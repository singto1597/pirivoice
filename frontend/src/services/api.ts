import axios from 'axios';

/**
 * Error ที่พก HTTP status มาด้วย
 *
 * ⚠️ **ทำไมต้องมี** — interceptor เดิมโยน `new Error(detail)` ล้วน ๆ ⇒ **status หายไป**
 *   ⇒ ผู้เรียกแยกไม่ออกระหว่าง "ไม่พบ/ถูกซ่อน" (404) กับ "เซิร์ฟเวอร์พัง" (500)
 *   ซึ่งเป็นเหตุผลที่บั๊ก #32 วินิจฉัยยาก: ทั้งสองอาการมาถึงหน้าเป็นข้อความก้อนเดียว
 *   ที่หน้าตาเหมือนกัน ⇒ ทางแก้ที่ปลายทางจึงมีได้แค่ "เด้งกลับหน้ารวม" ซึ่งผิดสำหรับ 500
 *
 * ✅ **เป็นส่วนเพิ่ม ไม่ใช่การเปลี่ยนสัญญา** — ยังเป็น `Error` จริง (`instanceof Error`
 *   ผ่านทุกที่) และ `.message` เหมือนเดิม ⇒ ผู้เรียกเดิมทั้งหมดไม่ต้องแก้แม้บรรทัดเดียว
 *
 * ⚠️ `status` เป็น `undefined` ได้ (เน็ตหลุด/timeout — ไม่มี response เลย)
 *   ⇒ ผู้เรียกต้องเทียบ `=== 404` ไม่ใช่ใช้ค่าตรง ๆ
 */
export interface ApiError extends Error {
  status?: number;
}

export const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000',
  headers: {
    'Accept': 'application/json',
    'Content-Type': 'application/json',
  },
});

// Interceptor ขาออก
api.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('access_token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

// Interceptor ขาเข้า: จัดการ Error และดักจับ 401
let isRedirectingToLogin = false;

api.interceptors.response.use(
  (response) => response.data,
  async (error) => {
    if (error.response) {
      if (error.response.status === 401) {
        // เคลียร์ Session ทั้งหมด (ไม่ใช่แค่ token) เพื่อป้องกัน redirect วนลูป
        localStorage.removeItem('access_token');
        localStorage.removeItem('user_id_str');

        if (!isRedirectingToLogin && !window.location.pathname.startsWith('/login')) {
          isRedirectingToLogin = true;
          window.location.href = '/login';
        }
      }

      let detail = error.response.data?.detail || 'เกิดข้อผิดพลาดจาก API';

      // 🔍 ตอน responseType:'blob' (เช่น ดาวน์โหลดไฟล์) body ของ error เป็น Blob ไม่ใช่ JSON
      // → ต้องแกะ JSON จาก Blob เอง ไม่งั้น user เห็นข้อความรวมๆ แทนข้อความจริงจาก backend
      if (error.response.data instanceof Blob) {
        try {
          const text = await error.response.data.text();
          const parsed = JSON.parse(text) as { detail?: unknown };
          if (parsed?.detail) detail = parsed.detail;
        } catch {
          /* body ไม่ใช่ JSON — ใช้ข้อความ default ต่อไป */
        }
      }

      // ปลดล็อก Pydantic 422 Error ให้อ่านรู้เรื่อง!
      if (Array.isArray(detail)) {
        detail = detail.map((err) => {
          const field = err.loc ? err.loc[err.loc.length - 1] : 'Unknown';
          return `ฟิลด์ '${field}': ${err.msg}`;
        }).join('\n');
      }

      // ⭐ แนบ status ไปกับ Error — ดู `ApiError` ข้างบน (ผู้เรียกเดิมไม่กระทบ)
      const apiError = new Error(detail) as ApiError;
      apiError.status = error.response.status;
      return Promise.reject(apiError);
    }
    // ไม่มี response เลย (เน็ตหลุด/timeout) ⇒ **ไม่ต้องใส่ status** ให้เป็น undefined
    // ผู้เรียกที่เทียบ `=== 404` จะได้ false ตามที่ควร — อย่าใส่ 0 หรือ -1 มั่ว ๆ
    return Promise.reject(new Error('ไม่สามารถเชื่อมต่อกับ Backend ได้: ' + error.message));
  }
);

export default api;
