# API Reference

ทุก endpoint ของ backend อยู่ในหน้านี้ ใช้เป็นที่ค้นตอนเขียนหน้าจอหรือต่อจากสคริปต์ภายนอก

- 🔌 **ทางเข้า** — ทุกเส้นขึ้นต้นด้วย `/api` ยกเว้นกลุ่มสาธารณะที่ `/api/v1` และ `/health`
- 🔐 **สิทธิ์** — บอกทุกเส้นว่าต้องล็อกอินไหม และต้องมีสิทธิ์อะไร
- 🧾 **รหัสสถานะ** — 401 กับ 403 ต่างกันตรงไหน แล้ว 400 กับ 422 ใครเป็นคนตอบ

## ใครใช้บทนี้

คนที่เรียก API จากหน้าจอหรือจากภายนอก และคนที่ต้องตอบให้ได้ว่าทำไมผู้ใช้คนนี้ได้ 401 แต่คนนั้นได้ 403

## ก่อนเริ่ม

- ค่าทั้งหมดมาจาก `backend/routers/` และ `backend/models/` ไม่ได้มาจากเอกสารออกแบบ
- ไม่มี pagination แบบ cursor — endpoint ที่มีหน้าใช้ `page` และ `page_size` เหมือนกันหมด
- ระบบตอบเวลาเป็น ISO 8601 พร้อมเขตเวลา แล้วหน้าจอค่อยแสดงเป็น `Asia/Bangkok`

## รูปแบบคำขอและคำตอบ

| หัวข้อ | รูปแบบ |
|---|---|
| ตัวยืนยัน | `Authorization: Bearer <jwt>` |
| ทางเลือกสำหรับงานระบบ | `X-API-Key: <key>` ให้ตัวตนแบบระบบที่ไม่มี `user_id` |
| ชนิดข้อมูล | `application/json` ยกเว้นดาวน์โหลด template และ SSE |
| รหัสติดตาม | ทุกคำตอบมี `X-Trace-Id` |
| ข้อผิดพลาด | `{"detail": "ข้อความ"}` |

รหัสสถานะที่ระบบใช้มีสิบตัว แต่สี่ตัวนี้เจอบ่อยสุด

| รหัส | เกิดเมื่อ |
|---|---|
| 200 | สำเร็จทั่วไป |
| 201 | สร้างรายการใหม่ในบาง endpoint |
| 204 | ลบสำเร็จและไม่ส่งเนื้อหา ใช้ที่ `DELETE /api/bookmarks/{id}` เท่านั้น |
| 400 | ข้อมูลไม่ผ่านเงื่อนไขทางธุรกิจ |
| 401 | ไม่มี token หรือ token ใช้ไม่ได้ |
| 403 | มีตัวตนแต่ไม่มีสิทธิ์ หรือไม่ถึงระดับ |
| 404 | ไม่พบรายการ หรือรายการถูกลบ |
| 409 | ชนกับสถานะปัจจุบัน เช่น โหวตซ้ำ |
| 422 | schema ไม่ผ่าน เช่น ขาดฟิลด์หรือชนิดผิด |
| 503 | ฐานข้อมูลหรือบริการส่วนประกอบใช้ไม่ได้ |

**400 กับ 422 ต่างกันที่คนตอบ** — 422 มาจาก Pydantic ก่อนถึง service และบอกชื่อฟิลด์ที่ผิด
ส่วน 400 มาจาก service และบอกเงื่อนไขทางธุรกิจเป็นภาษาไทย

## สรุปทุก endpoint

### ยืนยันตัวตน · `/api/auth`

| Method | Path | สิทธิ์ | คำขอ | คำตอบ |
|---|---|---|---|---|
| POST | `/api/auth/login` | ไม่ต้อง | `LoginRequest` (`username`, `password`) | `LoginResponse` |
| GET | `/api/auth/me` | ล็อกอิน | — | `UserOut` |
| POST | `/api/auth/change-password` | ล็อกอิน | `ChangePasswordRequest` (`old_password`, `new_password`) | `{"status":"ok","message":"เปลี่ยนรหัสผ่านสำเร็จ"}` |

### เรื่อง · `/api/issues`

| Method | Path | เงื่อนไข | คำขอ | คำตอบ |
|---|---|---|---|---|
| POST | `/api/issues` | ล็อกอิน และมีสิทธิ์แจ้งในระดับที่ขอ | `IssueCreateRequest` | `IssueOut` |
| GET | `/api/issues` | ล็อกอิน เห็นตามขอบเขต | query: สถานะ หมวด หน้า | `IssueListOut` |
| GET | `/api/issues/summary` | ล็อกอิน | — | `MyIssueSummaryOut` |
| GET | `/api/issues/orphaned-assignments` | `MANAGE_STUDENTS` และโหมด `school` | query: `year_id` | `OrphanedAssignmentsOut` |
| POST | `/api/issues/{id}/reassign` | `MANAGE_STUDENTS` และโหมด `school` | `ReassignRequest` | dict |
| GET | `/api/issues/{id}` | ล็อกอิน และมองเห็นเรื่องนี้ | — | `IssueOut` |
| PATCH | `/api/issues/{id}` | ผู้แจ้งเท่านั้น | `IssueUpdateRequest` | `IssueOut` |
| POST | `/api/issues/{id}/approve-to-public` | สภาหรือผู้ดูแล | `ApproveToPublicRequest` | dict |
| PATCH | `/api/issues/{id}/destination` | ผู้รับระดับห้องขึ้นไปหรือสภา | `ChangeDestinationRequest` | `IssueOut` |
| POST | `/api/issues/{id}/accept` | ระดับสูงพอและยังไม่มีผู้รับ | `CountdownSetRequest` | dict |
| PATCH | `/api/issues/{id}/countdown` | ผู้รับหรือผู้จัดการเรื่อง | `CountdownSetRequest` | dict |
| POST | `/api/issues/{id}/steps` | ผู้รับเรื่อง | `StepCreateRequest` | `IssueStepOut` |
| PATCH | `/api/issues/{id}/steps/{step_id}/complete` | ผู้รับเรื่อง | — | dict |
| POST | `/api/issues/{id}/escalate` | ผู้รับหรือผู้ดูแล | `EscalateRequest` | dict |
| POST | `/api/issues/{id}/resolve` | ผู้รับหรือผู้ดูแล | — | dict |
| POST | `/api/issues/{id}/cancel` | ผู้แจ้งหรือผู้ดูแล | — | dict |
| POST | `/api/issues/{id}/comments` | มองเห็นเรื่องนี้ | `CommentCreateRequest` (`body`) | `CommentOut` |
| PATCH | `/api/issues/{id}/comments/{comment_id}` | ผู้เขียนคอมเมนต์ | `CommentCreateRequest` | `CommentOut` |
| DELETE | `/api/issues/{id}/comments/{comment_id}` | ผู้เขียนคอมเมนต์ | — | dict |

### แดชบอร์ด · `/api/dashboard`

| Method | Path | เงื่อนไข | คำตอบ |
|---|---|---|---|
| GET | `/api/dashboard/summary` | `VIEW_DASHBOARD` | `DashboardSummary` |
| GET | `/api/dashboard/traffic` | `VIEW_DASHBOARD` และขอบเขต `all` หรือ `super` | `DashboardTraffic` |

### หน้าแรก · `/api/home`

| Method | Path | เงื่อนไข | คำตอบ |
|---|---|---|---|
| GET | `/api/home/summary` | ล็อกอิน | `HomeSummaryOut` |

### นักเรียนและห้อง · ไม่มี prefix เพิ่ม

| Method | Path | เงื่อนไข | คำขอ | คำตอบ |
|---|---|---|---|---|
| GET | `/api/students/me/profile` | ล็อกอิน | — | `MyProfileOut` |
| PATCH | `/api/students/me/profile` | ล็อกอิน | `UpdateProfileRequest` | `MyProfileOut` |
| GET | `/api/rooms` | `MANAGE_STUDENTS` | — | `list[RoomOut]` |
| GET | `/api/students` | `MANAGE_STUDENTS` | query: ปี ห้อง ตำแหน่ง คำค้น | `list[StudentOut]` |
| POST | `/api/students` | `MANAGE_STUDENTS` | `StudentCreateRequest` | dict (201) |
| PATCH | `/api/students/{student_id}` | `MANAGE_STUDENTS` และอันดับถึง | `StudentUpdateRequest` | dict |
| POST | `/api/students/bulk-move` | `MANAGE_STUDENTS` และอันดับถึง | `BulkMoveRequest` | dict |
| POST | `/api/students/unassign-room` | `MANAGE_STUDENTS` และอันดับถึง | `UnassignRoomsRequest` | dict |
| GET | `/api/students/{student_id}/history` | `MANAGE_STUDENTS` | — | `StudentHistoryOut` |

### นำเข้าจาก Excel · ไม่มี prefix เพิ่ม

| Method | Path | เงื่อนไข | คำขอ | คำตอบ |
|---|---|---|---|---|
| GET | `/api/import-student-template` | `MANAGE_STUDENTS` | — | ไฟล์ `.xlsx` |
| POST | `/api/upload-student-excel` | `MANAGE_STUDENTS` | `multipart/form-data` ฟิลด์ `file` | `ImportJobOut` |
| POST | `/api/start-import-job/{job_id}` | `MANAGE_STUDENTS` และเจ้าของงานหรือระดับสูงกว่า | — | `ImportJobOut` |
| GET | `/api/import-jobs` | `MANAGE_STUDENTS` | — | `list[ImportJobOut]` |

### บันทึกการใช้งาน · `/api/audit-logs`

| Method | Path | เงื่อนไข | คำขอ | คำตอบ |
|---|---|---|---|---|
| GET | `/api/audit-logs` | `VIEW_AUDIT_LOG` | query: `action`, `entity_type`, `user_id`, `status`, `start_date`, `end_date`, `page`, `page_size` | `AuditLogListOut` |

### บอร์ด · `/api/boards`

| Method | Path | เงื่อนไข | คำขอ | คำตอบ |
|---|---|---|---|---|
| GET | `/api/boards` | ล็อกอิน | query: ชนิด คำค้น หน้า | `BoardListOut` |
| GET | `/api/boards/reports` | ผู้จัดการบอร์ด | query: สถานะ หน้า | `ReportListOut` |
| GET | `/api/boards/{id}` | ล็อกอิน | — | `BoardDetailOut` |
| POST | `/api/boards/suggestions` | ล็อกอิน | `SuggestionCreateRequest` | `SuggestionCreatedOut` (201) |
| POST | `/api/boards/{id}/vote` | ล็อกอิน และยังไม่เคยโหวต | `VoteSubmitRequest` (`choice_id`) | `VoteResultOut` |
| POST | `/api/boards/{id}/comments` | ล็อกอิน และบอร์ดเปิดคอมเมนต์ | `CommentCreateRequest` (`body`, `parent_id`) | `BoardCommentOut` |
| POST | `/api/boards/{id}/comments/{cid}/report` | ล็อกอิน ไม่ใช่เจ้าของคอมเมนต์ | `ReportCreateRequest` | dict |
| POST | `/api/boards/{id}/comments/{cid}/hide` | ผู้จัดการบอร์ด | `HideCommentRequest` | dict |
| POST | `/api/boards/{id}/comments/{cid}/unhide` | ผู้จัดการบอร์ด | — | dict |
| POST | `/api/boards/{id}/hide` | ผู้จัดการบอร์ด | `HideBoardRequest` | dict |
| POST | `/api/boards/{id}/unhide` | ผู้จัดการบอร์ด | — | dict |
| POST | `/api/boards/reports/{report_id}/resolve` | ผู้จัดการบอร์ด | `ResolveReportRequest` | dict |

"ผู้จัดการบอร์ด" คือคนที่ผ่าน `board_moderation_service`
ได้แก่สภานักเรียน ประธานสภา ครูสภานักเรียน และผู้ดูแลระบบ

### บุ๊กมาร์ก · `/api/bookmarks`

| Method | Path | เงื่อนไข | คำขอ | คำตอบ |
|---|---|---|---|---|
| GET | `/api/bookmarks` | ล็อกอิน | query: `entity_type`, หน้า | `BookmarkListOut` |
| GET | `/api/bookmarks/status` | ล็อกอิน | query: `entity_type`, `entity_id` | `BookmarkStatusOut` |
| POST | `/api/bookmarks` | ล็อกอิน | `BookmarkCreateRequest` | `BookmarkOut` |
| DELETE | `/api/bookmarks/{id}` | เจ้าของรายการ | — | 204 ไม่มีเนื้อหา |

::: warning ลบถาวรแล้วกู้คืนไม่ได้
`DELETE /api/bookmarks/{id}` เป็น hard delete ตัวเดียวใน API นี้ — แถวหายจากตารางจริง ไม่มี `deleted_at` ให้กู้
ถ้าจะทำ endpoint ลบแบบใหม่ ให้ดูว่าโดเมนนั้นต้องการ soft delete หรือไม่ก่อน
:::

### แจ้งเตือน · `/api/notifications`

| Method | Path | เงื่อนไข | คำขอ | คำตอบ |
|---|---|---|---|---|
| GET | `/api/notifications` | ล็อกอิน | query: `group_type`, `page`, `page_size` | `NotificationListOut` |
| GET | `/api/notifications/unread-count` | ล็อกอิน | — | `UnreadCountsOut` |
| POST | `/api/notifications/read` | ล็อกอิน | `MarkReadRequest` | `MarkReadOut` |
| GET | `/api/notifications/preferences` | ล็อกอิน | — | `NotificationPreferencesOut` |
| PUT | `/api/notifications/preferences` | ล็อกอิน | `UpdateNotificationPreferencesRequest` | `NotificationPreferencesOut` |
| GET | `/api/notifications/push/status` | ล็อกอิน | — | `PushStatusOut` |
| POST | `/api/notifications/push/subscribe` | ล็อกอิน | `PushSubscriptionIn` | `PushSubscribeOut` |
| POST | `/api/notifications/push/unsubscribe` | ล็อกอิน | `PushUnsubscribeIn` | `PushUnsubscribeOut` |
| GET | `/api/notifications/stream` | ล็อกอิน | — | `text/event-stream` |

### ประกาศ · `/api/announcements`

| Method | Path | เงื่อนไข | คำขอ | คำตอบ |
|---|---|---|---|---|
| GET | `/api/announcements` | ล็อกอิน | query: `status` | `AnnouncementListOut` |
| POST | `/api/announcements` | `MANAGE_ANNOUNCEMENTS` | `AnnouncementCreateRequest` | `AnnouncementAdminOut` (201) |
| PATCH | `/api/announcements/{id}` | `MANAGE_ANNOUNCEMENTS` | `AnnouncementUpdateRequest` | `AnnouncementAdminOut` |
| DELETE | `/api/announcements/{id}` | `MANAGE_ANNOUNCEMENTS` | — | `AnnouncementAdminOut` |
| POST | `/api/announcements/{id}/restore` | `MANAGE_ANNOUNCEMENTS` | — | `AnnouncementAdminOut` |
| POST | `/api/announcements/{id}/retire` | `MANAGE_ANNOUNCEMENTS` | — | `AnnouncementAdminOut` |
| POST | `/api/announcements/{id}/unretire` | `MANAGE_ANNOUNCEMENTS` | — | `AnnouncementAdminOut` |

### ตั้งค่า · `/api/settings`

| Method | Path | เงื่อนไข | คำขอ | คำตอบ |
|---|---|---|---|---|
| GET | `/api/settings/quiet-hours` | ล็อกอิน | — | `QuietHoursOut` |
| PUT | `/api/settings/quiet-hours` | `MANAGE_SETTINGS` | `QuietHoursUpdateRequest` | `QuietHoursOut` |
| GET | `/api/settings/terms` | `MANAGE_SETTINGS` | — | `AcademicTermListOut` |
| POST | `/api/settings/terms` | `MANAGE_SETTINGS` | `AcademicTermCreateRequest` | `AcademicTermOut` (201) |
| PATCH | `/api/settings/terms/{id}` | `MANAGE_SETTINGS` | `AcademicTermUpdateRequest` | `AcademicTermOut` |
| POST | `/api/settings/terms/{id}/set-current` | `MANAGE_SETTINGS` | — | `AcademicTermOut` |
| DELETE | `/api/settings/terms/{id}` | `MANAGE_SETTINGS` | — | `AcademicTermOut` |
| POST | `/api/settings/terms/{id}/restore` | `MANAGE_SETTINGS` | — | `AcademicTermOut` |
| GET | `/api/settings/years` | `MANAGE_SETTINGS` หรือ `MANAGE_STUDENTS` | — | `AcademicYearListOut` |
| GET | `/api/settings/years/{id}` | เหมือนรายการ | — | `AcademicYearOut` |
| POST | `/api/settings/years` | `MANAGE_SETTINGS` | `AcademicYearCreateRequest` | `AcademicYearOut` (201) |
| PATCH | `/api/settings/years/{id}` | `MANAGE_SETTINGS` | `AcademicYearUpdateRequest` | `AcademicYearOut` |
| POST | `/api/settings/years/{id}/set-current` | `MANAGE_SETTINGS` | — | `AcademicYearOut` |
| DELETE | `/api/settings/years/{id}` | `MANAGE_SETTINGS` | — | `AcademicYearOut` |
| POST | `/api/settings/years/{id}/restore` | `MANAGE_SETTINGS` | — | `AcademicYearOut` |

### เลื่อนชั้น · `/api/rollover`

| Method | Path | เงื่อนไข | คำขอ | คำตอบ |
|---|---|---|---|---|
| POST | `/api/rollover/preview` | `MANAGE_STUDENTS` และโหมด `school` | `RolloverPreviewRequest` | `RolloverPreviewOut` |
| POST | `/api/rollover/apply` | เหมือน preview | `RolloverApplyRequest` | `RolloverApplyOut` |
| GET | `/api/rollover/runs` | เหมือน preview | query: ปีต้นทาง ปลายทาง | `RolloverRunListOut` |
| GET | `/api/rollover/reconciliation` | เหมือน preview | `year_id` | `ReconciliationOut` |

### โปรไฟล์ส่วนตัว · `/api/me`

| Method | Path | เงื่อนไข | คำตอบ |
|---|---|---|---|
| GET | `/api/me/stats` | ล็อกอิน | `PersonalStatsOut` |
| GET | `/api/me/activity` | ล็อกอิน | `ActivityListOut` |

### กิจกรรม · `/api/events`

| Method | Path | เงื่อนไข | คำขอ | คำตอบ |
|---|---|---|---|---|
| GET | `/api/events/public` | ล็อกอิน | query: `scope` (`upcoming`/`past`/`all`) | `EventPublicListOut` |
| GET | `/api/events/public/{id}` | ล็อกอิน | — | `EventPublicOut` |
| GET | `/api/events/{id}/my-registration` | ล็อกอิน | — | `MyRegistrationOut` |
| POST | `/api/events/{id}/register` | ล็อกอิน | — | `MyRegistrationOut` |
| DELETE | `/api/events/{id}/register` | ล็อกอิน | — | `MyRegistrationOut` |
| GET | `/api/events` | `MANAGE_EVENTS` | query: สถานะ หมวด | `EventListOut` |
| GET | `/api/events/{id}` | `MANAGE_EVENTS` | — | `EventOut` |
| POST | `/api/events` | `MANAGE_EVENTS` | `EventCreateRequest` | `EventOut` (201) |
| PATCH | `/api/events/{id}` | `MANAGE_EVENTS` | `EventUpdateRequest` | `EventOut` |
| DELETE | `/api/events/{id}` | `MANAGE_EVENTS` | — | `EventOut` |
| POST | `/api/events/{id}/publish` | `MANAGE_EVENTS` | — | `EventOut` |
| POST | `/api/events/{id}/cancel` | `MANAGE_EVENTS` | — | `EventOut` |
| POST | `/api/events/{id}/restore` | `MANAGE_EVENTS` | — | `EventOut` |
| GET | `/api/events/{id}/registrations` | `MANAGE_EVENTS` | — | `EventRegistrationListOut` |
| POST | `/api/events/{id}/check-in` | `MANAGE_EVENTS` | `CheckInRequest` | `CheckInResultOut` |

### สาธารณะ · `/api/v1/public` และสุขภาพระบบ

| Method | Path | สิทธิ์ | คำตอบ |
|---|---|---|---|
| GET | `/api/v1/public/stats` | ไม่ต้องล็อกอิน | `SystemStatsOut` |
| GET | `/api/v1/public/stats/trend` | ไม่ต้องล็อกอิน | `list[StatTrendPoint]` |
| GET | `/api/v1/public/resolved-cases` | ไม่ต้องล็อกอิน | `list[ResolvedCaseOut]` |
| GET | `/api/v1/public/announcements` | ไม่ต้องล็อกอิน | `list[AnnouncementOut]` |
| GET | `/health` | ไม่ต้องล็อกอิน | `{"status":"ok","database":"connected"}` |

## รายละเอียดที่ต้องรู้รายโมดูล

### ยืนยันตัวตน

- `login` ตอบ 404 `ไม่พบผู้ใช้` เมื่อไม่เจอชื่อผู้ใช้ และ 401 เมื่อรหัสผ่านผิด
- `login` เขียน `action='login'` ทั้งกรณีสำเร็จและล้มเหลว เอาไปใช้ทำสถิติการใช้งานได้
- `me` คืนข้อมูลผู้ใช้จาก token ไม่ต้องมีแถวสมาชิก
- `change-password` ตอบ 400 เมื่อรหัสใหม่ซ้ำรหัสเดิม และล้าง `must_change_password` ให้หลังเปลี่ยนสำเร็จ

### เรื่อง

- `GET /api/issues` กับ `GET /api/issues/{id}` ใช้กติกาเดียวกันคือ `_assert_can_view` — รวมพีระมิด คนที่เคยเกี่ยวข้อง และข้อจำกัดระดับชั้นของครู
- คนที่ไม่มีสิทธิ์ดูได้ 403 `คุณไม่มีสิทธิ์ดูเรื่องนี้` ไม่ใช่ 404 นะ
- `accept` ต้องมีอันดับไม่ต่ำกว่าระดับปัจจุบัน และเรื่องระดับห้องต้องเป็นสมาชิกห้องนั้น
  ไม่ผ่านจะได้ 403 `เรื่องนี้ไม่อยู่ในระดับของคุณ` หรือ 400 `เรื่องนี้มีผู้รับอยู่แล้ว`
- `escalate` ที่ระดับสภาตอบ 400 `เรื่องนี้อยู่ระดับสูงสุดแล้ว (สภานักเรียน) — ส่งต่อไม่ได้`
- `approve-to-public` รับเฉพาะเรื่องที่ `requested_destination` เป็น `vote` หรือ `talk`
  ถ้าเป็น `normal` จะได้ 400 และถ้าเคยเผยแพร่แล้วจะได้ 409
- `reassign` กับ `orphaned-assignments` ต้องเป็นโหมด `school` เท่านั้น ครูระดับชั้นจึงใช้ไม่ได้ แม้จะมี `MANAGE_STUDENTS`
- การรับเรื่อง ส่งต่อ ปิดเรื่อง และเปลี่ยนผู้รับ เขียน `issue_status_history` พร้อมแจ้งเตือนใน transaction เดียวกัน

::: tip เส้นทางคงที่ต้องมาก่อนเส้นทางที่มีพารามิเตอร์
`GET /api/issues/summary` ถูกประกาศก่อน `GET /api/issues/{id}` เสมอ
ถ้าเพิ่ม endpoint ใหม่ ให้วางไว้ก่อน `/{issue_id}` ไม่งั้น "summary" จะถูกแปลงเป็น int แล้วได้ 422
:::

### แดชบอร์ด

- `summary` ตอบ 403 `Access Denied: คุณไม่มีสิทธิ์ 'VIEW_DASHBOARD'` เมื่อขาดสิทธิ์
- `traffic` ตอบ 403 `คุณไม่มีสิทธิ์ดูข้อมูลการใช้งานของระบบ` เมื่อขอบเขตไม่ใช่ `all` หรือ `super`
- ทั้งสอง endpoint ใช้ขอบเขตแบบปิดเมื่อไม่รู้จัก คือให้เห็นน้อยที่สุด ไม่ใช่เห็นทั้งหมด

### นักเรียน

- `GET /api/rooms` กับ `GET /api/students` ใช้ `MANAGE_STUDENTS` และถูกจำกัดด้วยระดับชั้นสำหรับครูและประธานระดับ
- `PATCH /api/students/{id}` ตรวจอันดับด้วย `MANAGE_RANK` ก่อนแก้ คนที่อันดับต่ำกว่าจึงแก้อันดับสูงกว่าไม่ได้
- `bulk-move` กับ `unassign-room` รับได้เฉพาะปีการศึกษาปัจจุบัน และเขียน `student_moves`
- `history` รวมแถวข้ามปีและประวัติการย้ายในช่วงที่ระบบเก็บไว้

### นำเข้า

- `upload-student-excel` ตรวจชนิดไฟล์ ขนาดตาม `IMPORT_FILE_SIZE_LIMIT_MB` และจำนวนแถวตาม `IMPORT_MAX_ROWS`
- งานที่อัปโหลดได้สถานะ `PENDING` ต้องเรียก `start-import-job` ก่อนถึงจะเข้าคิว
- ข้อผิดพลาดรายแถวถูกเก็บใน `error_logs` และไม่ทำให้ทั้งไฟล์ล้ม
- `default_password` คือรหัสนักเรียนเมื่อไม่ได้ระบุ และผู้ใช้ต้องเปลี่ยนตอนล็อกอินครั้งแรก

### บอร์ด

- `vote` ตอบ 409 `คุณโหวต board นี้ไปแล้ว` เมื่อมีเสียงที่ยังไม่ถูกลบ
- `comments` รีพลายได้ลึกไม่เกินค่าที่ service กำหนด ถ้าเกินจะได้ 400 พร้อมชื่อขีดจำกัด
- `report` แจ้งคอมเมนต์ของตัวเองไม่ได้ และแจ้งคอมเมนต์เดิมซ้ำไม่ได้
- `hide` ซ่อนคอมเมนต์และรายการลูกทั้งหมด และนับเป็นผลการจัดการรายงาน

### ประกาศ

- รายการอ่านได้โดยคนที่ล็อกอิน และกรอง `status` ได้
- การเขียนทุกตัวต้องมี `MANAGE_ANNOUNCEMENTS` และเขียน audit ทุกครั้ง
- `retire` เอาออกจากหน้าแรกแต่ไม่ลบ ส่วน `restore` ใช้กู้รายการที่ลบแล้ว
- ประกาศ `urgent` ตั้ง `bypass_quiet_hours` เมื่อสร้างการแจ้งเตือน

### ตั้งค่า

- `quiet-hours` อ่านได้ทุกคนที่ล็อกอิน เขียนได้เฉพาะ `MANAGE_SETTINGS`
- `terms` กับ `years` ใช้ `MANAGE_SETTINGS` และบังคับ "ปัจจุบันมีตัวเดียว" ด้วย index
- `set-current` ล้างตัวเดิมก่อนตั้งตัวใหม่ใน transaction เดียว
- การเปลี่ยนปีปัจจุบันมีผลกับค่า default ของ `students.academic_year_id` สำหรับแถวใหม่

### เลื่อนชั้น

- `preview` ไม่เขียนข้อมูลโดเมน แต่บันทึกแถวใน `rollover_runs` สถานะ `PREVIEWED`
- `apply` ใช้ `run_id` จาก preview และตรวจว่าแผนยังตรงกับข้อมูลปัจจุบัน
- ต้องเป็นโหมด `school` และปีต้นทางต้องเป็นปีปัจจุบัน
- `reconciliation` ใช้ตรวจรายชื่อที่ยังไม่ถูกผูกปีหรือห้อง

### กิจกรรม

- `public` เป็นรายการที่เผยแพร่แล้วเท่านั้น และยังต้องล็อกอิน
- `register` ใส่คิวสำรองอัตโนมัติเมื่อเต็ม และคืนสถานะ `waitlisted`
- `check-in` รับ `token` จากคิวอาร์หรือ `registration_id` และปฏิเสธการสแกนซ้ำด้วยข้อความ `สถานะเปลี่ยนไปแล้ว กรุณาสแกนใหม่`
- `cancel` ของกิจกรรมเปลี่ยนสถานะเป็นยกเลิก ไม่ลบแถวลงทะเบียน

### สาธารณะ

- สี่ endpoint นี้ไม่ต้องล็อกอิน และไม่มีข้อมูลส่วนบุคคล
- `resolved-cases` ไม่แสดงชื่อผู้แจ้ง
- `stats/trend` คืนชุดจุดรายวันสำหรับกราฟหน้าแรก

## ข้อความผิดพลาดที่พบบ่อย

| ข้อความ | รหัส | เกิดเมื่อ |
|---|---|---|
| `Access Denied: ไม่พบข้อมูลของคุณ` | 403 | บัญชีไม่มีแถวสมาชิกที่ยังใช้งาน |
| `Access Denied: คุณไม่มีสิทธิ์ '<ชื่อ>'` | 403 | มีแถวแต่ตำแหน่งไม่มีสิทธิ์นั้น |
| `คุณไม่มีสิทธิ์ดูเรื่องนี้` | 403 | เรื่องอยู่นอกพีระมิดหรือต่างระดับชั้น |
| `เรื่องนี้ไม่อยู่ในระดับของคุณ` | 403 | กดรับเรื่องที่ระดับสูงกว่าตน |
| `เรื่องนี้มีผู้รับอยู่แล้ว` | 400 | กดรับเรื่องที่มีผู้รับแล้ว |
| `เรื่องนี้อยู่ระดับสูงสุดแล้ว (สภานักเรียน) — ส่งต่อไม่ได้` | 400 | ส่งต่อจากระดับสภา |
| `เฉพาะผู้แจ้งเรื่องเท่านั้นที่แก้ไขเรื่องนี้ได้` | 403 | แก้เรื่องที่ตัวเองไม่ได้แจ้ง |
| `คุณโหวต board นี้ไปแล้ว` | 409 | โหวตซ้ำ |
| `board นี้ปิดคอมเมนต์แล้ว` | 403 | คอมเมนต์ในบอร์ดที่ปิด |
| `คุณแจ้งคอมเมนต์นี้ไปแล้ว รอสภานักเรียนจัดการ` | 409 | แจ้งรายงานซ้ำ |
| `กิจกรรมนี้ยังไม่เปิดให้ลงทะเบียน` | 400 | ลงทะเบียนกิจกรรมฉบับร่าง |
| `เลยกำหนดลงทะเบียนแล้ว` | 400 | ลงทะเบียนหลังกำหนด |
| `รหัสเช็คอินไม่ถูกต้อง` | 400 | token ไม่ผ่านการตรวจ |
| `รูปแบบเวลาต้องเป็น HH:MM (เช่น 22:00)` | 400 | กรอกช่วงเวลาไม่ครบ |
| `ยังไม่มีปีการศึกษาปัจจุบัน` | 400 | เรียกงานที่ต้องใช้ปีปัจจุบัน |
| `คุณไม่มีสิทธิ์ดูบันทึกการใช้งาน` | 403 | เปิดบันทึกโดยไม่มี `VIEW_AUDIT_LOG` |

## ระบบทำอะไรเบื้องหลัง

- ทุกคำขอผ่าน middleware ที่ตั้ง `trace_id` แล้วแนบกลับมาเป็น `X-Trace-Id`
- mutation ทุกตัวเขียน audit ใน transaction เดียวกับข้อมูลหลัก
- การอ่านแดชบอร์ด บันทึกการใช้งาน และเรื่องบางประเภทถูกบันทึกแบบ best-effort
- endpoint ที่สร้างการแจ้งเตือนจะเพิ่มแถวใน `notifications` ซึ่งไปกระตุ้น outbox และ SSE ผ่าน trigger
- endpoint ที่เปลี่ยนสถานะเรื่องเขียน `issue_status_history` เสมอ
- SSE ใช้ `text/event-stream` และไม่ผ่าน `response_model`
- template นำเข้าเป็นไฟล์ทวิภาคและไม่ผ่าน `response_model` เช่นกัน

## ข้อจำกัดและข้อควรระวัง

- ไม่มี OpenAPI UI ที่เปิดสาธารณะใน production
- ไม่มี rate limit ต่อผู้ใช้ในตัว backend
- ไม่มี pagination แบบ cursor และไม่มีตัวกรองช่วงวันที่ในหน้ารวมเรื่อง
- `DELETE /api/bookmarks/{id}` เป็น hard delete และตอบ 204
- ไม่มี endpoint สำหรับลืมรหัสผ่านหรือตั้งรหัสผ่านแทนผู้ใช้
- ไม่มี endpoint อัปโหลดรูปในเรื่องหรือภาพปกกิจกรรม รับเป็น URL เท่านั้น
- ไม่มี endpoint ส่งออกข้อมูลเป็น Excel หรือ CSV ยกเว้น template นำเข้า
- `X-API-Key` ให้ตัวตนที่ไม่มี `user_id` และใช้ได้เฉพาะ endpoint ที่ไม่ต้องใช้เจ้าของ

## ติดปัญหาตรงไหน? ดูวิธีแก้ตรงนี้เลย

**Q: เรียก endpoint แล้วได้ 401 `Not authenticated: Bearer Token required`?**

👉 **วิธีแก้:** ไม่มีหัว `Authorization` หรือรูปแบบไม่ใช่ `Bearer <token>` — เช็กว่าหน้าจอแนบ token จาก `localStorage` จริง และ token ยังไม่หมดอายุ

**Q: ได้ 401 `Invalid or expired token`?**

👉 **วิธีแก้:** token หมดอายุ ถูกแก้ไข หรือลงนามด้วยคีย์อื่น ให้ล็อกอินใหม่ ถ้ายังเกิดกับทุกคน ให้ตรวจ `JWT_SECRET` ของทุก replica

**Q: ได้ 403 `Access Denied: ไม่พบข้อมูลของคุณ`?**

👉 **วิธีแก้:** บัญชีไม่มีแถวสมาชิกที่ยังใช้งานในปีการศึกษาใดเลย ไปดูที่หน้า **สมาชิก** ว่ามีรายชื่อและปีถูกต้องไหม

**Q: ได้ 422 แต่ส่ง JSON ครบ?**

👉 **วิธีแก้:** 422 มาจาก schema ไม่ใช่ service ส่วนมากเป็นชนิดข้อมูลผิด เช่นส่งวันที่เป็นสตริงผิดรูปแบบ หรือส่งค่าเกินช่วงที่ schema กำหนด เช่น `estimated_days` เกิน 365

**Q: เรียก `GET /api/issues/summary` แล้วถูกจับเป็น `{issue_id}`?**

👉 **วิธีแก้:** เส้นทางคงที่ถูกประกาศก่อนเส้นทางที่มีพารามิเตอร์เสมอ ถ้าเพิ่ม endpoint ใหม่ ให้วางไว้ก่อน `/{issue_id}` ไม่งั้นจะถูกแปลงเป็น int และได้ 422

**Q: ต้องการเรียก API จากสคริปต์ภายนอกโดยไม่มีผู้ใช้?**

👉 **วิธีแก้:** ใช้ `X-API-Key` แต่ตัวตนจะเป็นระบบและไม่มี `user_id` endpoint ที่ต้องใช้เจ้าของ เช่นบุ๊กมาร์กหรือแจ้งเตือน จะใช้ไม่ได้

**Q: ต้องรู้ว่าใครเรียก endpoint นี้ตอนไหน?**

👉 **วิธีแก้:** เอา `X-Trace-Id` จากคำตอบไปค้นใน **บันทึกการใช้งาน** ถ้าเป็น endpoint ที่อ่านข้อมูลและไม่บันทึก audit จะไม่มีแถว

**Q: เรียก `POST /api/events/{id}/check-in` แล้วได้ `สถานะเปลี่ยนไปแล้ว กรุณาสแกนใหม่`?**

👉 **วิธีแก้:** คนนั้นถูกเช็คอินไปแล้วหรือการลงทะเบียนถูกยกเลิก ให้ตรวจรายชื่อคนที่ลงทะเบียนก่อนสแกนซ้ำ

บทที่เกี่ยวข้อง: [การยืนยันตัวตนและสิทธิ์](auth-and-rbac.md) · [โครงสร้างฐานข้อมูล](database-schema.md) · [งานเบื้องหลัง การแจ้งเตือน และ push](background-jobs-and-push.md)
