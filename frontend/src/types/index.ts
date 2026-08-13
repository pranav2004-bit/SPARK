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

export type AuthUser = AdminUser | StudentUser | SuperAdminUser;

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

export type Department =
  | "CSD"
  | "CSM"
  | "CSE"
  | "CSC"
  | "ECE"
  | "IT"
  | "EEE"
  | "MECH"
  | "CIVIL"
  | "CHEM"
  | "BIOTECHNOLOGY";

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
  is_published: boolean;
  set_count: number;
  created_by: string;
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
  batch_id: string;
  institution_id: string;
  global_start_time: string | null;
  global_expire_time: string;
  exam_duration_minutes: number;
  pass_cutoff_percentage: number;
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
  status: BatchAssignmentStatus;
  exam_duration_minutes: number;
  global_start_time: string | null;
  global_expire_time: string;
  session_status: AssessmentSessionStatus | null;
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
  score: number | null;
  total_marks: number | null;
}

// ── Admin: Results (Phase 7) ─────────────────────────────────────────────────

export interface AdminResultRow {
  result_id: string;
  student_user_id: string;
  student_roll_id: string;
  student_name: string;
  department: string;
  started_at: string;
  ended_at: string;
  duration_seconds: number;
  score: number;
  total_marks: number;
  percentage: number;
  status: AssessmentSessionStatus;
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

export interface AdminActivityLogEntry {
  event_type: string;
  occurred_at: string;
  metadata: Record<string, unknown>;
}

export interface AdminResultLogsData {
  result_id: string;
  malpractice_flag: boolean;
  malpractice_reasons: string[];
  count: number;
  total_pages: number;
  current_page: number;
  logs: AdminActivityLogEntry[];
}
