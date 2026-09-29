"""📡 Notification stream hub — Postgres `LISTEN/NOTIFY` → SSE

**ปัญหาที่แก้:** badge ในแอพ (กระดิ่ง/ตัวเลขบนเมนู) อัปเดตด้วย **poll ทุก 30 วินาที**
(`stores/notifications.ts`) ⇒ คนที่เปิดแอพอยู่เห็นช้าได้ถึง 30 วิ และรู้สึกว่า
"ต้องรีเฟรช" · ไฟล์นี้ทำให้ **ขยับทันที** （~1 วิ）โดยไม่ต้อง poll ถี่ขึ้น

**คนละเรื่องกับ `push_service`:** push = "ปิดแอพอยู่ก็ยังเด้ง" (ผ่าน FCM/APNs ซึ่งมี
Doze/คิวของ OS เป็นพื้นทางกายภาพ) · stream = "เปิดแอพอยู่ badge ขยับทันที"
⇒ ทั้งสองอย่างต้องมีคู่กัน ไม่ใช่แทนกัน

## สถาปัตยกรรม — 1 connection ต่อโปรเซส ไม่ใช่ต่อผู้ใช้

    INSERT INTO notifications            (ใน transaction ของ caller)
       └─ trigger AFTER INSERT  →  pg_notify('piri_notifications', '{"user_id":7}')
                                        │  ★ ยิงตอน COMMIT เท่านั้น (rollback = ไม่มี event)
          backend replica (1 ใน 3)      │
             ├─ [conn เดียว] LISTEN ─────┘
             └─ dict {user_id: [Queue]}   ← fan-out ในโปรเซส
                    └─ GET /api/notifications/stream  (SSE)
                           └─ fetch + ReadableStream → อัปเดต badge

🚨 **ห้าม LISTEN ต่อผู้ใช้ 1 คน** — จะถือ DB connection ค้าง 1 ตัวต่อ 1 แท็บที่เปิด
   ⇒ 100 คนเปิดแอพ = 100 connection ค้าง (pool ระเบิด) และ SSE อยู่นานเป็นชั่วโมง
   ⇒ ที่นี่ใช้ **connection เดียวต่อโปรเซส** แล้ว fan-out ในหน่วยความจำ

🚨 **connection ของ listener ต้องไม่มาจาก pool** — ถ้ายืมจาก pool จะกินสล็อตค้าง
   ตลอดอายุโปรเซส (pool `max_size=10` ⇒ 1 ใน 10 หายไปถาวร) และ pool อาจสั่งปิด
   connection ที่ถูกยืมมานาน ⇒ ใช้ `asyncpg.connect()` ตรง ๆ แยกต่างหาก

## ⭐ event เป็น "สัญญาณ" ไม่ใช่ "ข้อมูล"

`Queue(maxsize=1)` โดยเจตนา ⇒ ถ้ามี event ซ้อนเข้ามาระหว่างที่ผู้บริโภคยังไม่ตื่น
**ตัวที่มาทีหลังจะถูกทิ้ง** (QueueFull → pass) — ปลอดภัยเพราะ:
  ฝั่ง client ไม่ได้ใช้ event เป็นข้อมูล แต่ใช้เป็นสัญญาณให้ไป **ถามยอดจริงจาก DB**
  (`get_unread_counts`) ⇒ การทิ้ง event ที่ซ้ำซ้อนไม่ทำให้ยอดเพี้ยน ทำได้แค่
  "ถามช้าลง" ซึ่งยอดที่ได้ก็ยังเป็นยอดปัจจุบันอยู่ดี

⇒ คุณสมบัตินี้คือเหตุที่ `maxsize=1` **ถูกต้อง ไม่ใช่การประหยัด**
   (ถ้า event เป็นข้อมูลจริง การทิ้งจะทำให้เพี้ยน — ที่นี่ไม่ใช่)

## ⚠️ ความล้มเหลวแบบเงียบ — ตัวที่ต้องระวังที่สุด

ถ้า connection ของ listener ตาย (DB restart / network) แล้วไม่มีใครต่อใหม่
**badge จะหยุดอัปเดตทันทีโดยไม่มี error ให้เห็น** — เป็นอาการเดียวกับที่ผู้ใช้บ่น
เรื่อง push มาช้า/หยุดกลางทางเป๊ะ ๆ ⇒ `_supervise()` เฝ้าด้วย
`add_termination_listener` แล้วต่อใหม่พร้อม backoff
· และ **ยังคง poll 30 วิไว้เป็นตาข่ายชั้นสอง** (ดู `stores/notifications.ts`) —
  stream เป็น "ทำให้เร็วขึ้น" ไม่ใช่ "แทน poll" ⇒ stream ตาย = กลับไปเป็น 30 วิ ไม่ใช่พัง
"""
from __future__ import annotations

import asyncio
import json
import logging

import asyncpg

from core.config import settings

logger = logging.getLogger("NOTIF_STREAM")

# ⭐ 1 = "ธง dirty" ไม่ใช่คิวงาน — ดูหัวข้อ "event เป็นสัญญาณ ไม่ใช่ข้อมูล" ข้างบน
_QUEUE_MAXSIZE = 1
# backoff ของการต่อใหม่: 1 → 2 → 4 → … → 30 วิ (เพดาน)
_RECONNECT_MIN = 1.0
_RECONNECT_MAX = 30.0


class StreamAtCapacity(RuntimeError):
    """ผู้ใช้ที่เปิด stream เกินเพดานของโปรเซสนี้ — router แปลงเป็น 503"""


class NotificationHub:
    """ทะเบียนผู้รับ SSE ในโปรเซสนี้ + connection ที่ LISTEN อยู่ตัวเดียว

    ⚠️ **ไม่ thread-safe และไม่ต้องเป็น** — ทั้งโปรเซสเป็น asyncio event loop เดียว
       ทุก mutation เกิดใน coroutine ⇒ ไม่มีการแย่งกันแบบแท้จริง
       (`list.add`/`discard` ไม่มี `await` คั่น ⇒ ไม่มีจุดที่สลับ context)
    """

    def __init__(
        self,
        *,
        channel: str | None = None,
        max_subscribers: int | None = None,
    ) -> None:
        self._channel = channel or settings.NOTIFY_CHANNEL
        self._max_subscribers = max_subscribers or settings.STREAM_MAX_SUBSCRIBERS
        # user_id → เซตของ queue (ผู้ใช้คนเดียวอาจเปิดหลายแท็บ/หลายเครื่อง)
        self._subscribers: dict[int, set[asyncio.Queue]] = {}
        self._conn: asyncpg.Connection | None = None
        self._supervisor: asyncio.Task | None = None
        self._dsn: str | None = None
        self._stopping = False
        # set() = connection ตายแล้ว และ supervisor ต้องต่อใหม่
        # 🚨 **สร้างใน `start()` ไม่ใช่ที่นี่** — ดูคำอธิบายยาวใน `start()`
        self._conn_lost: asyncio.Event | None = None
        self._stale_dropped = 0  # นับ event ที่ถูกทิ้งเพราะคิวเต็ม (วินิจฉัย)

    # ---------------- ข้อมูลสำหรับวินิจฉัย / เทสต์ ----------------

    @property
    def subscriber_count(self) -> int:
        """จำนวน *ผู้ใช้* ที่มี stream เปิดอยู่ (ไม่ใช่จำนวนแท็บ)"""
        return len(self._subscribers)

    @property
    def connection_count(self) -> int:
        """จำนวน queue ทั้งหมด (ผู้ใช้ 1 คนเปิด 3 แท็บ = 3)"""
        return sum(len(qs) for qs in self._subscribers.values())

    @property
    def is_connected(self) -> bool:
        return self._conn is not None and not self._conn.is_closed()

    @property
    def stale_dropped(self) -> int:
        """event ที่ถูกทิ้งเพราะคิวเต็ม — ปกติเป็น 0 · โต = ผู้บริโภคตามไม่ทัน"""
        return self._stale_dropped

    # ---------------- lifecycle ----------------

    async def start(self, dsn: str) -> None:
        """เริ่ม supervisor — **ไม่ raise ถ้าต่อไม่ได้**

        🚨 จงใจไม่ raise: ถ้า LISTEN ไม่ขึ้น ระบบยังต้องทำงานได้ (in-app ยังใช้ poll
           30 วิได้ปกติ) ⇒ การทำให้ lifespan ล้มเพราะเหตุนี้ = ปิดระบบทั้งระบบ
           เพื่อของประดับ ⇒ ต่อไม่ได้ = log ERROR แล้วลองใหม่เรื่อย ๆ ในเบื้องหลัง
        """
        if self._supervisor is not None:
            return  # idempotent — เรียกซ้ำได้ (TestClient/lifespan อาจเรียกหลายรอบ)
        self._dsn = dsn
        self._stopping = False
        # 🚨 **สร้างธงที่นี่ ทุกครั้งที่ start — ไม่ใช่ใน `__init__`** (สองเหตุผลคนละเรื่อง)
        #
        #  1. **asyncio primitive ผูกกับ event loop ตอน "ใช้งานครั้งแรก"** ไม่ใช่ตอนสร้าง
        #     ⇒ ถ้าสร้างใน `__init__` (ตอน import โมดูล ซึ่ง *ยังไม่มี* loop) แล้วนำไปใช้
        #     ข้าม loop จะได้ `RuntimeError: ... is bound to a different event loop`
        #     · เกิดจริงในเทสต์ (TestClient สร้าง loop ใหม่ทุกเคส) และจะเกิดกับโปรเซส
        #     ที่รัน lifespan ซ้ำ (reload / reuse โมดูล)
        #  2. **ต้องเป็นธงใหม่สะอาด** — ธงเดิมถูกตั้งค้างไว้โดย `stop()` รอบก่อน
        #     (การปิด connection ของเราเองก็ trigger termination listener)
        #     ⇒ ถ้าสืบทอดธงเก่ามา supervisor จะตื่นทันทีที่ `wait()` แล้ววนเปิด-ปิดไม่หยุด
        #     เป็นลูปแน่นที่กิน CPU เต็ม โดยที่ log ดูเหมือน "ต่อใหม่ปกติ" (จับได้ตอนรันเทสต์)
        self._conn_lost = asyncio.Event()
        self._supervisor = asyncio.create_task(self._supervise(), name="notif-stream-supervisor")
        # 🚨 ดักการตายแบบไม่คาดคิด — ดู docstring ของ `_on_supervisor_done()`
        self._supervisor.add_done_callback(self._on_supervisor_done)
        logger.info("📡 notification stream: supervisor started (channel=%s)", self._channel)

    @staticmethod
    def _on_supervisor_done(task: "asyncio.Task[None]") -> None:
        """🚨 supervisor ตาย = badge กลับไปเป็น 30 วิ **ตลอดไป** โดยที่ทุกอย่างดูปกติ

        นี่คือความล้มเหลวแบบเงียบชนิดที่โมดูลนี้ถูกสร้างขึ้นมาป้องกัน ⇒ การ์ดที่เฝ้า
        ความล้มเหลวแบบเงียบ **ต้องไม่ตายเงียบเอง** · ปกติ `stop()` เป็นคนยกเลิก
        (ได้ `CancelledError` — ไม่ใช่เรื่องผิดปกติ) แต่ exception อื่นแปลว่ามีบั๊ก
        ⇒ ต้อง ERROR ให้เห็นในlog ไม่ใช่ปล่อยให้ badge ช้าเงียบ ๆ
        """
        if task.cancelled():
            return  # ทางปกติตอน shutdown — ไม่ต้องรายงาน
        exc = task.exception()
        if exc is not None:
            logger.error(
                "🚨 notification stream: supervisor ตายกลางทาง — badge จะกลับไปเป็น "
                "30 วิ จนกว่าจะรีสตาร์ตโปรเซส",
                exc_info=exc,
            )

    async def stop(self) -> None:
        """ปิดอย่างสุภาพ — ยกเลิก supervisor, ปิด connection, ล้างผู้ฟังทั้งหมด"""
        self._stopping = True
        if self._conn_lost is not None:
            # ปลุก supervisor ที่กำลังรออยู่ ให้เห็นธง stopping
            # (อาจเป็น None ถ้า `stop()` ถูกเรียกก่อน `start()` — เช่น lifespan ล้มตอนเปิด)
            self._conn_lost.set()
        if self._supervisor is not None:
            self._supervisor.cancel()
            try:
                await self._supervisor
            except asyncio.CancelledError:
                pass
            except Exception:  # noqa: BLE001 — supervisor ตายไปก่อนแล้ว (มี log จาก
                # done-callback) ⇒ อย่าให้ขยะของมันไปทำให้ **shutdown ของ lifespan ล้ม**
                # · หลักเดียวกับ `_close_conn()` ข้างล่าง: ปิดไม่สำเร็จก็ช่างมัน
                logger.debug("📡 supervisor จบด้วย exception (รายงานไปแล้ว)", exc_info=True)
            self._supervisor = None
        await self._close_conn()
        self._subscribers.clear()
        logger.info("📡 notification stream: stopped")

    # ---------------- ผู้รับ ----------------

    def at_capacity(self, user_id: int) -> bool:
        """ตรวจเพดาน**โดยไม่ลงทะเบียน** — ให้ router ตอบ 503 ได้อย่างสะอาด

        ⚠️ ต้องมีคู่กับ `subscribe()` เพราะสองจังหวะนี้แยกกันจริง:
           `subscribe()` ถูกเรียก **ใน** generator (เพื่อให้ `finally` ถอนผู้ฟังได้เสมอ
           แม้ client ตัดการเชื่อมต่อก่อน byte แรกจะออกไป) — ซึ่งตอนนั้น HTTP status
           ถูกส่งไปแล้ว ⇒ ตอบ 503 ไม่ได้ · จึงต้องเช็คล่วงหน้าที่นี่
           การเช็คสองที่มีเจตนา: ที่นี่เพื่อ "ตอบให้ถูก", ที่ `subscribe()` เพื่อ "กันจริง"
        """
        if user_id in self._subscribers:
            return False  # มีแท็บเปิดอยู่แล้ว = ไม่กินที่เพิ่ม
        return len(self._subscribers) >= self._max_subscribers

    def subscribe(self, user_id: int) -> asyncio.Queue:
        """ลงทะเบียนรับ event ของ `user_id` — คืน queue ที่ endpoint จะ await

        ⚠️ เพดานนับที่ **จำนวนผู้ใช้** ไม่ใช่จำนวนแท็บ — ถ้าคนเดียวกันเปิด 20 แท็บ
           ก็ยังนับเป็น 1 (ไม่ให้คนเดียวไล่คนอื่นออกจากระบบ)
        """
        queues = self._subscribers.get(user_id)
        if queues is None:
            if len(self._subscribers) >= self._max_subscribers:
                logger.warning(
                    "📡 notification stream: ถึงเพดานผู้ฟัง (%d) — ปฏิเสธผู้ใช้ %s",
                    self._max_subscribers, user_id,
                )
                raise StreamAtCapacity(
                    f"เปิด stream พร้อมกันเกินเพดานของเซิร์ฟเวอร์ ({self._max_subscribers})"
                )
            queues = set()
            self._subscribers[user_id] = queues

        q: asyncio.Queue = asyncio.Queue(maxsize=_QUEUE_MAXSIZE)
        queues.add(q)
        return q

    def unsubscribe(self, user_id: int, q: asyncio.Queue) -> None:
        """ถอนผู้ฟัง — **ต้องเรียกใน `finally` ของ generator เสมอ**

        ถ้าลืม: แท็บที่ปิดไปแล้วจะค้างใน dict ตลอดอายุโปรเซส ⇒ memory โตไม่หยุด
        และ `_publish` จะเอา event ไปใส่คิวที่ไม่มีใครอ่าน (ช้าแต่ไม่พัง — อันตราย
        เพราะไม่มีอาการให้เห็น)
        """
        queues = self._subscribers.get(user_id)
        if not queues:
            return
        queues.discard(q)
        if not queues:
            # ลบ key ทิ้ง ไม่งั้น dict โตด้วย key ที่มีเซตว่าง
            self._subscribers.pop(user_id, None)

    # ---------------- เผยแพร่ ----------------

    def _publish(self, user_id: int) -> None:
        """ใส่สัญญาณให้ทุก queue ของผู้ใช้คนนั้น — ทิ้งถ้าคิวเต็ม (ดู docstring บนสุด)"""
        for q in self._subscribers.get(user_id, ()):
            try:
                q.put_nowait(None)  # ตัว event ไม่มีความหมาย — เป็นแค่ "ตื่นได้แล้ว"
            except asyncio.QueueFull:
                # ⭐ ปกติ ไม่ใช่ความผิดพลาด — มีสัญญาณค้างอยู่แล้ว 1 อัน = เพียงพอ
                self._stale_dropped += 1

    async def _on_notify(
        self, _conn: asyncpg.Connection, _pid: int, _channel: str, payload: str
    ) -> None:
        """callback ของ `LISTEN` — 🚨 **ห้าม raise เด็ดขาด**

        asyncpg จะ log exception ที่หลุดออกจาก callback แต่จะ **ไม่** ทำให้ connection
        ตาย ⇒ ถ้า raise ตรงนี้จะได้ log ท่วมโดยที่ stream ยังดูปกติ (หาเรื่องยาก)
        payload มาจาก DB ที่เราเชื่อถือ แต่ก็ยังไม่ควรพังทั้ง callback เพราะ JSON เพี้ยน
        """
        try:
            data = json.loads(payload)
            user_id = data.get("user_id")
            if not isinstance(user_id, int):
                logger.warning("📡 payload ไม่มี user_id ที่ใช้ได้: %r", payload[:120])
                return
            self._publish(user_id)
        except Exception:  # noqa: BLE001 — กันไม่ให้ callback โยนออกไปเด็ดขาด
            logger.exception("📡 ประมวลผล NOTIFY ไม่สำเร็จ (payload=%r)", payload[:120])

    # ---------------- connection ----------------

    async def _open_conn(self) -> None:
        conn = await asyncpg.connect(self._dsn)
        # ⭐ สัญญาณตายของ connection — ดีกว่า polling `is_closed()` ทุก N วินาที
        #    เพราะรู้ทันทีที่ตาย ไม่ใช่รู้ตอนถึงรอบตรวจ (ช่วงที่ยังไม่รู้ = badge เงียบ)
        conn.add_termination_listener(lambda _c: self._conn_lost.set())
        await conn.add_listener(self._channel, self._on_notify)
        self._conn = conn
        logger.info("📡 notification stream: LISTEN %s พร้อมใช้งาน", self._channel)

    async def _close_conn(self) -> None:
        conn, self._conn = self._conn, None
        if conn is None:
            return
        try:
            if not conn.is_closed():
                await conn.remove_listener(self._channel, self._on_notify)
                await conn.close()
        except Exception:  # noqa: BLE001 — ปิดไม่สำเร็จก็ช่างมัน อย่าให้ล้มตอน shutdown
            logger.debug("📡 ปิด connection ของ listener ไม่สำเร็จ", exc_info=True)

    async def _supervise(self) -> None:
        """ต่อ LISTEN ใหม่เรื่อย ๆ — ตัวกันความล้มเหลวแบบเงียบ (ดู docstring บนสุด)"""
        lost = self._conn_lost
        # รับประกันโดย `start()` (เป็นคนสร้าง task นี้) — ผูกไว้ในตัวแปรเพราะใช้ 5 จุด
        # ⚠️ ต้องใช้ `lost` ให้ครบทุกจุด ไม่ใช่กลับไปอ่าน `self._conn_lost` —
        #    ถ้าอ่านซ้ำ type checker จะไม่รู้ว่า assert ข้างบนรับประกันอะไรให้
        #    (และ assert ก็กลายเป็นพิธีกรรมที่ไม่คุ้มอะไร)
        assert lost is not None, "start() ต้องถูกเรียกก่อน _supervise()"
        delay = _RECONNECT_MIN
        while not self._stopping:
            if not self.is_connected:
                # 🚨 ล้างธง **ก่อน** เปิด connection ใหม่ ไม่ใช่หลัง
                #    `_close_conn()` ที่เราเรียกเองก็ trigger termination listener ⇒ ธงถูกตั้ง
                #    ค้าง ⇒ ถ้าล้างหลัง `_open_conn()` จะมีช่องว่างที่ connection ตายพอดี
                #    แล้วถูกล้างทิ้ง = รอตลอดกาลบน connection ที่ตายแล้ว (แย่กว่าเดิม)
                #    · ล้างก่อน = สัญญาณจากอดีตถูกทิ้ง ส่วนสัญญาณที่เกิดหลังเปิดยังมาถึงเสมอ
                lost.clear()
                try:
                    await self._open_conn()
                    delay = _RECONNECT_MIN  # สำเร็จ = รีเซ็ต backoff
                except asyncio.CancelledError:
                    raise
                except Exception as e:  # noqa: BLE001
                    # ERROR ไม่ใช่ WARNING: ระหว่างนี้ badge จะ *ไม่* ทันที (กลับเป็น 30 วิ)
                    # ⇒ ต้องรู้ ไม่ใช่ต้องสงสัย
                    logger.error(
                        "📡 ต่อ LISTEN ไม่สำเร็จ (จะลองใหม่ใน %.0f วิ): %s", delay, e
                    )
                    await self._sleep_or_stop(lost, delay)
                    delay = min(delay * 2, _RECONNECT_MAX)
                    continue

            # ต่อติดแล้ว — รอจนกว่าจะตาย (หรือถูกสั่งหยุด)
            await lost.wait()
            if self._stopping:
                return
            lost.clear()
            logger.warning("📡 connection ของ listener หลุด — กำลังต่อใหม่")
            await self._close_conn()

    async def _sleep_or_stop(self, lost: asyncio.Event, seconds: float) -> None:
        """นอนแบบปลุกได้ทันทีเมื่อถูกสั่งหยุด (ไม่งั้น shutdown จะรอนานสุด 30 วิ)

        ⚠️ รับ `lost` เป็น **argument** ไม่ใช่ไปอ่าน `self._conn_lost` เอง — ตามเหตุผล
           ที่ `_supervise()` เขียนกำกับไว้: ตัวแปรที่ `assert` ผ่านมาแล้วเท่านั้นที่
           type checker รับประกันให้ · อ่าน attribute ซ้ำ = narrowing หายทั้งที่ยังต้องใช้
        """
        try:
            await asyncio.wait_for(lost.wait(), timeout=seconds)
        except asyncio.TimeoutError:
            pass


# singleton ระดับโมดูล — `main.py` เป็นคน start/stop
# (เทสต์สร้าง instance ใหม่เองได้ผ่าน `NotificationHub(...)` โดยไม่แตะตัวนี้)
hub = NotificationHub()
