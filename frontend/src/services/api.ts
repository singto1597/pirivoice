import axios, { type AxiosResponse, type InternalAxiosRequestConfig } from 'axios';
import { REDIRECT_QUERY, safeRedirect } from '@/router/redirect';
import {
  buildCacheKey,
  clearQueryCache,
  deleteCacheEntry,
  getCacheEntry,
  invalidateForMutation,
  isCacheableData,
  isCurrentEntry,
  makeCachedResponse,
  markSynced,
  reconcile,
  writeCache,
} from './queryCache';

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

/**
 * 🧠 cache hit → ตอบจาก memory ทันที (จบใน microtask ก่อน paint) แล้วค่อย revalidate เงียบ ๆ
 *
 * ⚠️ ห้าม cache คำขอที่ `responseType` ไม่ใช่ json (blob/arraybuffer) — ข้อมูลไบนารี
 *   ไม่ควรถูกห่อด้วย reactive proxy และมักเป็นการดาวน์โหลดที่ต้องสด
 */
api.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('access_token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }

    const method = (config.method ?? 'get').toLowerCase();
    const responseType = config.responseType ?? 'json';
    if (method === 'get' && !config.noCache && responseType === 'json' && config.url) {
      const key = buildCacheKey(config.url, config.params, token);
      config.__cacheKey = key;
      const entry = getCacheEntry(key);
      if (entry) {
        // แทน adapter = ไม่ยิง network เลย แต่ response ยังไหลผ่าน transform ปกติ
        config.adapter = () => Promise.resolve(makeCachedResponse(config, entry.data));
        config.__fromCache = true;
      }
    }
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

/**
 * ยิงคำขอสดเบื้องหลังแล้ว reconcile ทับ proxy เดิมของ entry
 *
 * - dedupe ต่อ key ด้วย `entry.revalidating` (cache hit หลายครั้งรัว ๆ ไม่ยิงถี่กว่า 1)
 * - `isCurrentEntry` กันกรณี mutation ลบ entry ไปแล้วระหว่างรอ → ห้าม resurrect ข้อมูลเก่า
 * - 403/404 = ของหาย/ถูกซ่อนแล้ว ⇒ ลบ entry ไม่ให้หน้าโชว์ค้าง (401 มี interceptor จัดการ)
 */
function scheduleRevalidate(config: InternalAxiosRequestConfig, key: string): void {
  const entry = getCacheEntry(key);
  if (!entry || entry.revalidating) return;
  entry.revalidating = true;
  void (api.request({
    url: config.url,
    method: 'get',
    params: config.params,
    noCache: true,
  }) as unknown as Promise<unknown>)
    .then((fresh) => {
      if (!isCurrentEntry(key, entry) || !isCacheableData(fresh)) return;
      reconcile(entry.data, fresh);
      if (config.url) markSynced(config.url);
    })
    .catch((err: unknown) => {
      const status = (err as { status?: number }).status;
      if (status === 403 || status === 404) deleteCacheEntry(key);
    })
    .finally(() => {
      entry.revalidating = false;
    });
}

/**
 * ⚠️ ลำดับสำคัญมาก: cache miss ต้องคืน **proxy ตัวเดียวกับที่เก็บ** ไม่ใช่ `response.data`
 *   ดิบ ๆ — ไม่งั้น reconcile จะ mutate object ที่ไม่มีใครถือ reference แล้วหน้าจอไม่ขยับ
 */
function handleSuccess(response: AxiosResponse): unknown {
  const config = response.config;

  if (config.__fromCache && config.__cacheKey) {
    scheduleRevalidate(config, config.__cacheKey);
    return response.data;
  }

  const method = (config.method ?? 'get').toLowerCase();
  if (method !== 'get') {
    invalidateForMutation(config.url);
    return response.data;
  }

  if (config.__cacheKey && config.url && isCacheableData(response.data)) {
    markSynced(config.url);
    return writeCache(config.__cacheKey, config.url, response.data).data;
  }
  return response.data;
}

/**
 * 🔗 สร้าง URL ของหน้า Login **พร้อมจำปลายทางที่ผู้ใช้ตั้งใจจะไป** (§30)
 *
 * ⚠️ **ทำไมต้องมี** — 401 เป็นเส้นทางที่ **อยู่นอก router ทั้งหมด**: เกิดตอนที่ผู้ใช้
 *   *มี* token อยู่แล้วแต่มันหมดอายุ ⇒ guard (`router/index.ts`) เห็น `isAuthenticated = true`
 *   ⇒ **ไม่ยิง** ⇒ ผู้ใช้เข้าหน้าเป้าหมายได้ ⇒ พอยิง API ก็ได้ 401 ⇒ ถูกพาออกไปหน้า Login
 *   **โดยไม่มีใครรู้ว่าเขาจะไปไหน** ⇒ ล็อกอินเสร็จได้ `route.query.redirect === undefined`
 *   ⇒ `safeRedirect()` คืน `null` ⇒ ตกลงที่หน้าแรก (Home) — ซึ่งเป็นอาการที่ผู้ใช้รายงานตรง ๆ:
 *   *"มันจะเด้งไป login แล้วพอ login เสร็จ มันก็จะเข้าหน้า home"*
 *   ⇒ เส้นทางนี้ **guard ไม่มีทางแก้ให้ได้** เพราะมันไม่เคยถูกเรียกเลย
 *
 * 🔒 **ค่าที่เขียนต้องผ่านด่าน `safeRedirect()` ตัวเดียวกับที่หน้า Login ใช้** — ไม่ใช่
 *   "กติกาเดียวกันที่เขียนซ้ำ" แต่เป็น **ฟังก์ชันเดียวกัน** ⇒ สองฝั่งเพี้ยนจากกันไม่ได้
 *   (`pathname` มาจากเบราว์เซอร์ = ข้อมูลที่ผู้ใช้ควบคุมได้ เช่นเดียวกับ `?redirect=`)
 *   ⇒ หน้าที่ไม่ผ่านด่าน (ไม่ขึ้นต้น `/app/` เช่นหน้า public, หรือมี `\`) จะได้ `/login` เปล่า ๆ
 *     ตามพฤติกรรมเดิม — **ไม่ใช่ค่าแปลก ๆ ที่หน้า Login ต้องมาปฏิเสธเอง**
 *
 * ⚠️ `search` ต้องติดไปด้วย — ไม่งั้น deep link ที่พา query มา (`?tab=comments`) จะถึงหน้า
 *   ปลายทางแต่ **ไม่ถึงแท็บที่ตั้งใจ** = "เกือบถูก" ซึ่งดูเหมือนบั๊กของปลายทาง
 */
export function loginUrlRemembering(pathname: string, search: string): string {
  const target = safeRedirect(pathname + search);
  if (!target) return '/login';
  return `/login?${REDIRECT_QUERY}=${encodeURIComponent(target)}`;
}

// Interceptor ขาเข้า: จัดการ Error และดักจับ 401
let isRedirectingToLogin = false;

api.interceptors.response.use(
  // ⚠️ signature ของ axios บังคับให้คืน `AxiosResponse` แต่ทั้งโปรเจกต์ใช้ค่าที่ unwrap แล้ว
  //   (`services/*` ทุกตัวคาดว่าได้ data ตรง ๆ) ⇒ cast ครั้งเดียวตรงจุดนี้เท่านั้น
  (response) => handleSuccess(response) as unknown as typeof response,
  async (error) => {
    if (error.response) {
      if (error.response.status === 401) {
        // เคลียร์ Session ทั้งหมด (ไม่ใช่แค่ token) เพื่อป้องกัน redirect วนลูป
        // + ล้าง cache กันข้อมูลของผู้ใช้คนก่อนโผล่ให้คนถัดไปในแท็บเดียวกัน
        clearQueryCache();
        localStorage.removeItem('access_token');
        localStorage.removeItem('user_id_str');

        if (!isRedirectingToLogin && !window.location.pathname.startsWith('/login')) {
          isRedirectingToLogin = true;
          window.location.href = loginUrlRemembering(window.location.pathname, window.location.search);
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
