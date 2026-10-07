"""
กันถอยหลัง: ARQ worker ทั้งสองตัวต้องไม่แชร์คิวกัน

🐛 บั๊กที่เทสต์ชุดนี้กัน (พบ 7 ต.ค. 2026 บน staging — มีมาก่อนและกระทบ production ด้วย)
--------------------------------------------------------------------------------
`import_worker` กับ `push_worker` ต่างไม่ตั้ง `queue_name` และใช้ `REDIS_URL` ตัวเดียวกัน
⇒ ARQ ใช้ค่า default `arq:queue` ให้ทั้งคู่ และดึงงานออกจาก Redis list แบบ **atomic**
⇒ งาน 1 ชิ้นไปถึง worker เพียงตัวเดียว อีกตัวไม่รู้จักฟังก์ชันนั้นก็ log
`function ... not found` แล้ว **ทิ้งงานถาวร**

หลักฐานจาก staging:
  import_worker : 18:27:48: job cron:process_push_outbox:..., function 'cron:process_push_outbox' not found
  push_worker   : job c6011799d8bc4b39b2a47e2c1f108aa7, function 'process_student_import' not found
พิสูจน์ได้ด้วยการสเกล push_worker = 0 → งาน import ที่ค้างอยู่จบใน 0–3 วินาที

ทำไมอาการนี้แย่: `POST /api/start-import-job` ตอบ **200**, DB ขึ้น `QUEUED`, ครูไม่เห็น
error เลย — แต่งานหายไปครึ่งหนึ่ง (แล้วแต่ดวงว่างานตกฝั่งไหน)

บทเรียนที่เทสต์นี้ฝังไว้: invariant ไม่ใช่ "ค่าต้องสวย" แต่คือ **"ผู้ส่งกับผู้รับต้องตรงกัน"**
⇒ จึงเทสต์ทั้งสองด้าน ไม่ใช่เทสต์แค่ว่า queue_name ต่างกัน
"""
import pytest
from arq.constants import default_queue_name

from core.queues import IMPORT_QUEUE, PUSH_QUEUE
from services import import_service
from workers.import_worker import WorkerSettings as ImportWorkerSettings
from workers.push_worker import WorkerSettings as PushWorkerSettings


# ============================================================
# ① ฝั่งผู้รับ — worker สองตัวต้องฟังคนละคิว
# ============================================================
# ⚠️ อ่านผ่าน getattr โดยเจตนา — "ไม่มี attribute" กับ "มีแต่ค่าเป็น default"
#    ให้ผลเหมือนกันเป๊ะในรันไทม์ (ARQ ถอยไปใช้ `arq:queue` เงียบ ๆ ทั้งสองกรณี)
#    ⇒ เทสต์ต้องเห็นสองกรณีเป็นเรื่องเดียวกัน ไม่ใช่ AttributeError ที่อ่านไม่ออก
IMPORT_WORKER_QUEUE = getattr(ImportWorkerSettings, "queue_name", default_queue_name)
PUSH_WORKER_QUEUE = getattr(PushWorkerSettings, "queue_name", default_queue_name)


def test_workers_listen_on_different_queues():
    """สอง worker ต้องไม่ฟังคิวเดียวกัน — ถ้าซ้ำ งานจะถูกทิ้งแบบสุ่มครึ่งหนึ่ง"""
    assert IMPORT_WORKER_QUEUE != PUSH_WORKER_QUEUE, (
        f"import_worker กับ push_worker ฟังคิว '{IMPORT_WORKER_QUEUE}' เหมือนกัน "
        "⇒ งานจะถูกทิ้งสลับกัน (นี่คือบั๊กเดิม — ดู docstring ของไฟล์นี้)"
    )


@pytest.mark.parametrize(
    "worker_name, queue_name",
    [("import_worker", IMPORT_WORKER_QUEUE),
     ("push_worker", PUSH_WORKER_QUEUE)],
)
def test_worker_does_not_use_arq_default_queue(worker_name, queue_name):
    """ห้ามใช้ `arq:queue` — เพราะค่านั้นคือ "คิวที่ทุกตัวที่ลืมตั้งค่าจะแชร์กัน"

    ⚠️ เทสต์นี้จะ fail ถ้ามีคนลบ `queue_name` ออกจาก WorkerSettings
       (การลบทำให้ ARQ ย้อนกลับไปใช้ default เงียบ ๆ — ไม่มี error ตอนบูต)
    """
    assert queue_name != default_queue_name, (
        f"{worker_name}.WorkerSettings ไม่ได้ตั้ง queue_name ⇒ ตกลงไปใช้ "
        f"'{default_queue_name}' ร่วมกับ worker อีกตัว"
    )


def test_queue_names_are_distinct_constants():
    """ค่าคงที่ใน core/queues.py ต้องไม่ซ้ำกันเอง (กันพิมพ์ผิดจนกลายเป็นค่าเดียวกัน)"""
    assert IMPORT_QUEUE != PUSH_QUEUE


# ============================================================
# ② ฝั่งผู้ส่ง — enqueue ต้องระบุคิวเดียวกับที่ import_worker ฟัง
# ============================================================
class _FakeArqRedis:
    """ArqRedis ปลอม — ดักจับว่า enqueue_job ถูกเรียกด้วยคิวอะไร

    เก็บ `_queue_name` ไว้ตรวจ เพราะนี่คือพารามิเตอร์ที่ "ลืมแล้วเงียบ" —
    `enqueue_job` คืน None ทั้งตอนสำเร็จและตอนลงคิวที่ไม่มีใครฟัง
    """

    def __init__(self):
        self.calls = []

    async def enqueue_job(self, function, *args, **kwargs):
        self.calls.append({"function": function, "args": args, "queue": kwargs.get("_queue_name")})

    async def aclose(self):
        pass


@pytest.mark.asyncio
async def test_enqueue_import_job_targets_the_queue_import_worker_listens_on(monkeypatch):
    """หัวใจของบั๊ก: ตั้ง queue_name ที่ worker ถูกแล้ว แต่ถ้าฝั่งส่งไม่ระบุคิว ก็ยังหายอยู่ดี

    เทสต์นี้ผูกสองฝั่งเข้าด้วยกัน — ผ่านเฉพาะเมื่อ **ผู้ส่งยิงเข้าคิวเดียวกับที่ผู้รับฟัง**
    """
    fake = _FakeArqRedis()

    async def _fake_create_arq_redis():
        return fake

    monkeypatch.setattr(import_service, "create_arq_redis", _fake_create_arq_redis)

    await import_service.enqueue_import_job(4242)

    assert len(fake.calls) == 1, "ต้อง enqueue ครั้งเดียว"
    call = fake.calls[0]

    # ชื่อฟังก์ชันต้องตรงกับ __qualname__ ของ task (เดิมก็มี invariant นี้อยู่)
    assert call["function"] == "process_student_import"

    # ⭐ บรรทัดที่บั๊กเดิมจะตก
    assert call["queue"] is not None, (
        "enqueue_job ไม่ได้ระบุ _queue_name ⇒ งานลงคิว "
        f"'{default_queue_name}' ที่ import_worker ไม่ฟัง = หายเงียบ"
    )
    assert call["queue"] == IMPORT_WORKER_QUEUE, (
        f"ผู้ส่งยิงเข้าคิว '{call['queue']}' แต่ผู้รับฟัง "
        f"'{IMPORT_WORKER_QUEUE}' ⇒ งานไม่มีวันถูกประมวลผล"
    )
