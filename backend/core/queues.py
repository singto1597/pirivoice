"""
ชื่อ ARQ queue — แหล่งความจริงเดียวของทั้งสองฝั่ง (ผู้ส่ง + ผู้รับ)

⚠️ ทำไมต้องมีไฟล์นี้ แทนที่จะปล่อยให้เป็นค่า default
--------------------------------------------------------------
ARQ จะใช้ `arq:queue` เป็นชื่อคิวเริ่มต้น **เมื่อไม่ตั้ง `queue_name`** และมันดึงงาน
ออกจาก Redis list แบบ atomic ⇒ **งาน 1 ชิ้นไปถึง worker เพียงตัวเดียวเท่านั้น**

เดิมที `import_worker` กับ `push_worker` ต่างไม่ตั้ง `queue_name` และใช้ `REDIS_URL`
ตัวเดียวกัน ⇒ ทั้งคู่กินคิวเดียวกัน พองาน import ตกไปถึง push_worker (ซึ่งไม่รู้จัก
`process_student_import`) มันจะ log `function ... not found` แล้ว **ทิ้งงานถาวร**
และกลับกัน cron ของ push ก็ถูก import worker ทิ้งทุก 20 วินาที

อาการที่ผู้ใช้เห็นแย่เป็นพิเศษ: `POST /api/start-import-job` ตอบ **200**, DB ขึ้น
`QUEUED`, ครูไม่เห็น error เลย — แต่งานหายไปครึ่งหนึ่ง (แล้วแต่ดวงว่าตกฝั่งไหน)

⇒ ตั้งชื่อคิวให้แยกกันเด็ดขาด และ **ผู้ส่งต้องระบุคิวเดียวกับที่ผู้รับฟัง**
   (`enqueue_job(..., _queue_name=IMPORT_QUEUE)`) ไม่งั้นงานลงคิวเดิมที่ไม่มีใครกิน
   ซึ่งเป็นอาการเดียวกับบั๊กเดิมเป๊ะ — เงียบ ไม่มี error

คู่ที่ต้องตรงกัน (แก้ข้างเดียว = พัง):

| คิว | ผู้รับ (`WorkerSettings.queue_name`) | ผู้ส่ง |
|---|---|---|
| `IMPORT_QUEUE` | `workers/import_worker.py` | `services/import_service.enqueue_import_job` |
| `PUSH_QUEUE` | `workers/push_worker.py` | ARQ เอง (cron ยัดเข้าคิวของ worker ตัวนั้นอยู่แล้ว) |

มีเทสต์กันถอยหลังอยู่ที่ `tests/test_worker_queue_isolation.py`
"""

# คิวงานนำเขา Excel — worker ตั้ง max_jobs=1 (สร้าง users ชนกันได้)
IMPORT_QUEUE = "arq:queue:import"

# คิวงานส่ง push notification — worker ตั้ง max_jobs=2 (claim ด้วย FOR UPDATE SKIP LOCKED)
PUSH_QUEUE = "arq:queue:push"
