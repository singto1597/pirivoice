// 🧩 ชนิดข้อมูลที่ใช้ร่วมกันระหว่างคอมโพเนนต์ใน `components/ui/`
//
// ⚠️ แยกออกมาเป็นไฟล์ `.ts` ไม่ใช่ `export` จากใน `<script setup>` — เพราะ
//    `<script setup>` ไม่รองรับ ES module export (คอมไพเลอร์ของ Vue ฟ้อง
//    "<script setup> cannot contain ES module exports") ⇒ ถ้าประกาศในนั้น
//    จะ import จากที่อื่นไม่ได้เลย

/** ตัวเลือกหนึ่งแท็บใน `AppTabs` */
export interface AppTabOption {
  key: string
  /** ป้ายสั้น — ไทยล้วน (ห้าม `uppercase`/`tracking-*` กับภาษาไทย) */
  label: string
  /** ตัวเลขมุมขวาบน — 0/ไม่ระบุ = ไม่แสดง */
  badge?: number
}
