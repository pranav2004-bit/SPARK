// ── Auth ───────────────────────────────────────────────────────────────────────

export interface AdminUser {
  id: string;
  email: string;
  name: string;
  role: "admin";
  force_password_change?: boolean;
}

export interface StudentUser {
  student_id: string;
  role: "student";
  is_profile_completed: boolean;
  fullname?: string;
  force_password_change?: boolean;
}

export interface SuperAdminUser {
  id: string;
  email: string;
  name: string;
  role: "super_admin";
  institution_id: string;
  institution_name: string;
  force_password_change?: boolean;
}

export interface ITUser {
  id: string;
  email: string;
  name: string;
  role: "it";
  force_password_change?: boolean;
}

export type AuthUser = AdminUser | StudentUser | SuperAdminUser | ITUser;

export interface TokenPair {
  access_token: string;
  refresh_token: string;
}

export interface AdminLoginResponse {
  success: true;
  data: TokenPair & { user: AdminUser };
}

export interface StudentLoginResponse {
  success: true;
  data: TokenPair & { user: StudentUser };
}

export interface SuperAdminLoginResponse {
  success: true;
  data: TokenPair & { user: SuperAdminUser };
}

export interface ITLoginResponse {
  success: true;
  data: TokenPair & { user: ITUser };
}

// ── API ────────────────────────────────────────────────────────────────────────

export interface ApiSuccess<T> {
  success: true;
  data: T;
  message?: string;
}

export interface ApiError {
  success: false;
  message: string;
  errors?: Record<string, string[]>;
}

export interface PaginatedResponse<T> {
  count: number;
  total_pages: number;
  current_page: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

// ── Models ─────────────────────────────────────────────────────────────────────

export interface Batch {
  id: string;
  batch_name: string;
  student_count?: number;
  created_at: string;
  updated_at: string;
}

// Backend-managed since 2026-08-20 (IT's Departments module) — no longer a
// fixed compile-time union. Valid values come from GET /auth/departments/
// at runtime (see @/lib/departmentsContext), not from this type.
export type Department = string;

export interface DepartmentRecord {
  id: string;
  code: string;
  name: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface Student {
  id: string;
  student_id: string;
  fullname: string;
  college_email_id: string;
  department: Department;
  batch_id: string;
  batch_name?: string;
  is_active: boolean;
  is_profile_completed: boolean;
  created_at: string;
  updated_at: string;
}

export interface Company {
  id: string;
  company_name: string;
  is_published: boolean;
  section_count?: number;
  created_at: string;
  updated_at: string;
}

export interface Section {
  id: string;
  company_id: string;
  section_name: string;
  upload_count?: number;
  created_at: string;
  updated_at: string;
}

export type UploadType =
  | "pdf"
  | "audio"
  | "video"
  | "image"
  | "video_link"
  | "external_link";

export type ScanStatus = "pending" | "clean" | "infected" | "error";

export interface Upload {
  id: string;
  section_id: string;
  upload_type: UploadType;
  file_url: string;
  read_url: string;
  original_filename: string | null;
  file_size_bytes: number | null;
  scan_status: ScanStatus;
  created_at: string;
  updated_at: string;
}

// ── Student Profile ────────────────────────────────────────────────────────────

export interface StudentProfile {
  student_id: string;
  fullname: string;
  college_email_id: string;
  department: Department;
  batch_id: string;
  batch_name: string;
  is_profile_completed: boolean;
}

export interface StudentProfileUpdateResponse {
  profile: StudentProfile;
  access_token: string;
  refresh_token: string;
}

// ── Inquiry ────────────────────────────────────────────────────────────────────

export interface Inquiry {
  id: string;
  student_id: string;
  fullname: string;
  college_email_id: string;
  department: string;
  batch_name: string;
  message: string;
  is_read: boolean;
  created_at: string;
}

// ── Scroll Updates ─────────────────────────────────────────────────────────────

export interface ScrollConfig {
  is_enabled: boolean;
  direction: "left" | "right";
  updated_at: string;
}

export interface ScrollUpdate {
  id: string;
  text: string;
  link: string;
  show_new_badge: boolean;
  order: number;
  created_at: string;
  updated_at: string;
}

export interface StudentScrollResponse {
  is_enabled: boolean;
  direction: "left" | "right";
  updates: ScrollUpdate[];
}

// ── Resource Modules ───────────────────────────────────────────────────────────

export interface ResourceModule {
  id: string;
  name: string;
  is_published: boolean;
  is_system: boolean;
  order: number;
  created_at: string;
  updated_at: string;
}

// ── Practice ──────────────────────────────────────────────────────────────────

export interface PracticeModule {
  id: string;
  name: string;
  parent: string | null;
  is_published: boolean;
  order: number;
  created_at: string;
  updated_at: string;
}

export interface PracticeSection {
  id: string;
  name: string;
  module: string | null;
  is_published: boolean;
  order: number;
  question_count: number;
  created_at: string;
  updated_at: string;
}

export type ExplanationType      = "none" | "text" | "image" | "both";
export type QuestionContentType  = "text" | "image" | "both";
export type ProgressStatus       = "not_visited" | "visited" | "attempted" | "completed";
export type McqType              = "single" | "multiple";

export interface PracticeQuestionOption {
  id: string;
  label: string;
  text: string;
  order: number;
  // is_correct only present in admin responses — never in student responses
  is_correct?: boolean;
  question?: string;
  created_at?: string;
  updated_at?: string;
}

export interface PracticeQuestion {
  id: string;
  section: string;
  question_number: number;
  title: string;
  question_type: "mcq" | "fib";
  // MCQ sub-type
  mcq_type: McqType;
  // Question body
  question_content_type: QuestionContentType;
  question_text: string;
  question_image_key: string;
  question_image_url: string | null;
  // FIB answer (admin only — stripped from student responses)
  fib_answer: string;
  // Explanation
  explanation_type: ExplanationType;
  explanation_text: string;
  explanation_image_key: string;
  explanation_image_url: string | null;
  // Meta
  is_published: boolean;
  order: number;
  created_at: string;
  updated_at: string;
}

// ── Assessments ────────────────────────────────────────────────────────────────

export interface QuestionPaper {
  id: string;
  title: string;
  description: string;
  instructions: string;
  set_count: number;
  created_by: string;
  // Resolved server-side from created_by (a bare user_id — no FK across
  // services) via a best-effort auth-service lookup. Both can be "" if the
  // lookup didn't resolve (e.g. auth-service was briefly unreachable) —
  // never assume either is populated just because the paper loaded.
  created_by_name: string;
  created_by_email: string;
  created_at: string;
  updated_at: string;
}

export interface QuestionSet {
  id: string;
  paper: string;
  label: string;
  order: number;
  question_count: number;
  total_marks: number;
  section_count: number;
}

export interface QuestionSection {
  id: string;
  set: string;
  title: string;
  order: number;
  question_count: number;
}

export type AssessmentQuestionContentType = "text" | "image" | "both";
export type AssessmentMcqType = "single" | "multiple";
export type AssessmentOptionContentType = "text" | "image";

export interface AssessmentQuestionOption {
  id: string;
  question: string;
  label: string;
  content_type: AssessmentOptionContentType;
  text: string;
  image_key: string;
  image_url: string | null;
  is_correct: boolean;
  order: number;
  created_at: string;
  updated_at: string;
}

export interface AssessmentQuestion {
  id: string;
  set: string;
  section: string;
  question_number: number;
  question_type: "mcq";
  mcq_type: AssessmentMcqType;
  question_content_type: AssessmentQuestionContentType;
  question_text: string;
  question_image_key: string;
  question_image_url: string | null;
  question_image_size_bytes: number | null;
  marks: number;
  created_at: string;
  updated_at: string;
}

export type BatchAssignmentStatus = "SCHEDULED" | "LIVE" | "CLOSED";

export interface BatchAssignment {
  id: string;
  paper: string;
  paper_title: string;
  batch_id: string;
  institution_id: string;
  global_start_time: string | null;
  global_expire_time: string;
  exam_duration_minutes: number;
  pass_cutoff_percentage: number;
  show_result_to_student: boolean;
  // Empty array means every department in the batch — non-empty narrows
  // the roster snapshot to just those department(s).
  departments: string[];
  status: BatchAssignmentStatus;
  created_by: string;
  created_at: string;
  updated_at: string;
}

export interface BatchAssignmentStatusPoll {
  status: BatchAssignmentStatus;
  student_count_total: number;
  // Populated since Task 5.1 (AssessmentSession exists) — optional only
  // for backward compatibility with the type's pre-5.1 shape.
  student_count_completed?: number;
}

export type AssessmentSessionStatus =
  | "IN_PROGRESS" | "SUBMITTED" | "AUTO_SUBMITTED" | "EXPIRED_UNSTARTED";

export interface StudentAssignmentListItem {
  assignment_id: string;
  paper_title: string;
  paper_instructions: string;
  status: BatchAssignmentStatus;
  exam_duration_minutes: number;
  global_start_time: string | null;
  global_expire_time: string;
  session_status: AssessmentSessionStatus | null;
  // Added 2026-08-27 for the pre-exam briefing screen — from this
  // student's own allocated set specifically (see the backend's own
  // comment on StudentAssignmentListView for why that's always accurate).
  total_marks: number;
  question_count: number;
}

export interface StudentStartSessionResponse {
  session_id: string;
  ends_at: string;
  status: AssessmentSessionStatus;
}

export interface StudentQuestionOption {
  id: string;
  label: string;
  content_type: AssessmentOptionContentType;
  text: string;
  image_key: string;
  image_url: string | null;
  order: number;
}

export interface StudentQuestion {
  id: string;
  question_number: number;
  mcq_type: AssessmentMcqType;
  question_content_type: AssessmentQuestionContentType;
  question_text: string;
  question_image_url: string | null;
  marks: number;
  options: StudentQuestionOption[];
  selected_option_ids: string[];
  section_id: string;
  section_title: string;
}

export interface StudentSessionQuestionsResponse {
  session_id: string;
  session_status: AssessmentSessionStatus;
  ends_at: string;
  questions: StudentQuestion[];
}

export interface StudentSubmitResponse {
  session_id: string;
  status: AssessmentSessionStatus;
  results_visible: boolean;
  score: number | null;
  total_marks: number | null;
}

// ── Admin: Mock/Trial Exam Sessions (added 2026-08-27) ───────────────────────
// An admin dry-run on a paper they own — no assignment, no roster, no
// malpractice tracking. Reuses StudentSessionQuestionsResponse/
// StudentQuestion/StudentQuestionOption above (the trial questions endpoint
// returns the identical shape) — only the start/submit/results-list shapes
// differ from their student counterparts.

export interface AdminTrialStartResponse {
  session_id: string;
  ends_at: string;
  status: AssessmentSessionStatus;
  set_label: string;
}

export interface AdminTrialSubmitResponse {
  session_id: string;
  status: AssessmentSessionStatus;
  score: number | null;
  total_marks: number | null;
}

export interface AdminTrialResultRow {
  id: string;
  set_label: string;
  score: number;
  total_marks: number;
  percentage: number;
  duration_seconds: number;
  ended_at: string;
  attempted_by_name: string;
  attempted_by_email: string;
}

// ── Admin: Results (Phase 7) ─────────────────────────────────────────────────

export type AdminResultExamStatus = "pending" | "writing" | "submitted";

export interface AdminResultsPage extends PaginatedResponse<AdminResultRow> {
  // The full set-label roster for this assignment, independent of whatever
  // filters (including ?set= itself) narrowed `results` — lets the Set
  // filter dropdown stay populated even when a set filter is applied.
  available_sets: string[];
}

export interface AdminResultRow {
  result_id: string | null;
  session_id: string | null;
  student_user_id: string;
  student_roll_id: string;
  student_name: string;
  department: string;
  set_label: string;
  exam_status: AdminResultExamStatus;
  started_at: string | null;
  ended_at: string | null;
  duration_seconds: number | null;
  score: number | null;
  total_marks: number | null;
  percentage: number | null;
  malpractice_flag: boolean;
}

export interface AdminResultResponseQuestion {
  question_id: string;
  question_number: number;
  question_text: string;
  question_image_url: string | null;
  marks: number;
  options: Array<{
    id: string; label: string; content_type: AssessmentOptionContentType;
    text: string; image_key: string; image_url: string | null;
    is_correct: boolean; order: number;
  }>;
  selected_option_ids: string[];
  is_correct: boolean;
  marks_awarded: number;
  answered: boolean;
}

export interface AdminResultResponsesData {
  result_id: string;
  questions: AdminResultResponseQuestion[];
}

export interface AdminQuestionResponseStudent {
  student_user_id: string;
  student_roll_id: string;
  student_name: string;
  department: string;
  exam_status: AdminResultExamStatus;
  selected_option_ids: string[];
  is_correct: boolean;
  answered: boolean;
}

export interface AdminQuestionResponsesData {
  question_id: string;
  question_number: number;
  set_label: string;
  question_text: string;
  question_image_url: string | null;
  marks: number;
  options: AdminResultResponseQuestion["options"];
  count: number;
  total_pages: number;
  current_page: number;
  students: AdminQuestionResponseStudent[];
}

export interface AdminSessionTimelineEvent {
  description: string;
  occurred_at: string;
}

// The plain-English "logs/tracking" popup's data — keyed by session_id
// (not result_id), since it also covers a student who's still mid-exam.
export interface AdminSessionTimelineData {
  session_id: string;
  exam_status: string;
  malpractice_flag: boolean;
  malpractice_reasons: string[];
  total_event_count: number;
  truncated: boolean;
  retention_days: number;
  events: AdminSessionTimelineEvent[];
}
