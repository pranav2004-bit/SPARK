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
  // Mandatory since 2026-11-12 — every assignment declares its own start
  // time, driving the auto-start sweep (assessment-service's
  // sweep_scheduled_assignments_to_live). Still `string | null` in the
  // StudentAssignmentListItem variant below, which isn't affected by that
  // change.
  global_start_time: string;
  global_expire_time: string;
  exam_duration_minutes: number;
  pass_cutoff_percentage: number;
  show_result_to_student: boolean;
  // Set once, the moment an admin publishes results for an assignment
  // created with show_result_to_student=false — null means either "still
  // hidden" or "visible since creation" (never explicitly published).
  results_published_at: string | null;
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

// ── Essay Writing (essay-service) ────────────────────────────────────────────
// Phase 2 (Question Bank) only — no created_by_name/email resolution (no
// per-paper ownership restriction in this service, unlike QuestionPaper
// above) and no instructions field (not part of this service's scope).

export interface EssayPaper {
  id: string;
  title: string;
  description: string;
  set_count: number;
  created_by: string;
  created_at: string;
  updated_at: string;
}

export interface EssaySet {
  id: string;
  paper: string;
  label: string;
  order: number;
  has_question: boolean;
}

export interface EssayQuestion {
  id: string;
  set: string;
  question_text: string;
  llm_rubric_prompt: string;
  word_limit: number;
  time_limit_minutes: number;
  max_score: number;
  created_at: string;
  updated_at: string;
}

// Phase 3 — no exam_duration_minutes (unlike assessment-service's
// BatchAssignment): each EssaySet's own EssayQuestion already carries its
// own time_limit_minutes (Task 2.1), so there's nothing to duplicate here.
export interface EssayAssignment {
  id: string;
  paper: string;
  paper_title: string;
  batch_id: string;
  institution_id: string;
  global_start_time: string | null;
  global_expire_time: string;
  departments: string[];
  status: "SCHEDULED" | "LIVE" | "CLOSED";
  created_by: string;
  created_at: string;
  updated_at: string;
}

// ── Essay Writing — Student Exam Experience (Phase 4) ───────────────────────

export interface StudentEssayAssignmentListItem {
  assignment_id: string;
  paper_title: string;
  status: "SCHEDULED" | "LIVE" | "CLOSED";
  global_start_time: string | null;
  global_expire_time: string;
  attempt_status: "IN_PROGRESS" | "SUBMITTED" | "AUTO_SUBMITTED" | "EXPIRED_UNSTARTED" | null;
  word_limit: number | null;
  time_limit_minutes: number | null;
}

export interface EssayAttemptStartResponse {
  attempt_id: string;
  ends_at: string;
  status: "IN_PROGRESS" | "SUBMITTED" | "AUTO_SUBMITTED";
}

// Phase 14, Task 14.1 — Student Past Results. `feedback` mirrors
// EssayScore.feedback's own JSON contract (essay-service, ADR 003
// Decision 2): { overall, breakdown: { <criterion>: { score, maxScore,
// feedback } } }. `breakdown` keys are admin-defined rubric criteria
// names, not a fixed enum.
export interface EssayScoreCriterionFeedback {
  score: number;
  maxScore: number;
  feedback: string;
}

export interface EssayScoreFeedback {
  overall: string;
  breakdown: Record<string, EssayScoreCriterionFeedback>;
}

export interface StudentEssayResultRow {
  assignment_id: string;
  attempt_id: string;
  paper_title: string;
  set_label: string;
  question_text: string;
  attempt_status: "SUBMITTED" | "AUTO_SUBMITTED";
  // Reused verbatim from the admin Results module's own 4-bucket
  // vocabulary (essay-service's _essay_result_exam_status /
  // _SUBMISSION_STATUS_BUCKETS) — this view's own attempt is always
  // terminal (never "pending"/"writing", the other two values that
  // function can return for a non-terminal attempt), but the SUBMISSION
  // it's paired with genuinely can be "pending" too: EssaySubmission
  // defaults to that status for the real, if brief, window between
  // finalize_attempts() creating the row and the dispatched task actually
  // picking it up — found missing from this type during Phase 14's fourth
  // audit round. "pending"/"processing"/"failed" all mean "no score yet"
  // and the frontend treats the first two identically (both fall through
  // to the same generic message); "failed" gets its own distinct,
  // administrator-pointing message. The frontend never shows "failed"
  // literally to a student (reads as "you failed", not "grading hit an
  // error").
  exam_status: "pending" | "processing" | "completed" | "failed";
  started_at: string;
  submitted_at: string | null;
  score: number | null;
  max_score: number | null;
  is_no_submission: boolean;
  feedback: EssayScoreFeedback | null;
}

// Never includes llm_rubric_prompt — see StudentEssayQuestionSerializer's
// own docstring (essays/serializers.py) for why.
export interface StudentEssayQuestion {
  id: string;
  question_text: string;
  word_limit: number;
  time_limit_minutes: number;
  max_score: number;
}

export interface EssayAttemptDetail {
  attempt_id: string;
  ends_at: string;
  status: "IN_PROGRESS" | "SUBMITTED" | "AUTO_SUBMITTED";
  draft_response: string;
  question: StudentEssayQuestion | null;
}

// ── Admin: Submissions Module (Phase 6) ─────────────────────────────────────

export type EssaySubmissionStatusBucket = "pending" | "processing" | "completed" | "failed";

export interface EssaySubmissionsOverview {
  pending: number;
  processing: number;
  completed: number;
  failed: number;
  total: number;
}

// Real underlying pipeline status (essays/models.py's own
// SUBMISSION_STATUS_CHOICES) — distinct from the 4-bucket rollup above,
// which is what the overview widget and the list's own ?status= filter
// use; this is what a single row's own "status" field actually is.
// REPORT_GENERATING added Phase 11 — the brief (normally sub-second)
// in-between state while a report is being rendered.
export type EssaySubmissionStatus = "PENDING" | "LLM_PROCESSING" | "LLM_COMPLETE" | "LLM_FAILED" | "REPORT_GENERATING" | "REPORT_READY";

export interface EssaySubmissionListRow {
  id: string;
  status: EssaySubmissionStatus;
  student_id: string;
  attempt_id: string;
  assignment_id: string;
  batch_id: string;
  paper_title: string;
  malpractice_flag: boolean;
  score: number | null;
  created_at: string;
  updated_at: string;
}

export interface EssaySubmissionEvent {
  id: string;
  event_type: "STATUS_CHANGE" | "DLQ_RECORDED" | "ADMIN_RETRIGGER" | "ADMIN_OVERRIDE" | "EMAIL_BOUNCED" | "EMAIL_COMPLAINT";
  detail: string;
  worker_hostname: string;
  task_id: string;
  // Phase 7 — populated only on the two admin-initiated event types above.
  admin_user_id: string | null;
  reason: string;
  occurred_at: string;
}

export type EssayEvaluatedBy = "llm" | "admin";

export interface EssaySubmissionDetail {
  id: string;
  status: EssaySubmissionStatus;
  student_id: string;
  attempt_id: string;
  assignment_id: string;
  batch_id: string;
  paper_title: string;
  question_text: string;
  draft_response: string;
  malpractice_flag: boolean;
  malpractice_reasons: string[];
  score: number | null;
  feedback: { overall: string; breakdown?: Record<string, { score: number; maxScore: number; feedback: string }> } | null;
  // Phase 7 — "visibly distinguishable from an LLM-assigned score in
  // every later view"; null until a score exists either way.
  evaluated_by: EssayEvaluatedBy | null;
  has_llm_trace: boolean;
  events: EssaySubmissionEvent[];
  created_at: string;
  updated_at: string;
}

export interface EssaySubmissionsPipelineHealth {
  redis_ok: boolean;
  queue_depth: number | null;
  celery_workers_online: number;
  unresolved_dlq_count: number;
  oldest_unresolved_dlq_age_seconds: number | null;
  undispatched_submission_count: number;
  oldest_undispatched_submission_age_seconds: number | null;
}

// ── Admin: LLM Controls Module (Phase 7) ────────────────────────────────────

export interface EssayLLMTrace {
  prompt_messages: { role: string; content: string }[];
  raw_response: string;
  request_id: string;
  model_used: string;
  evaluated_at: string;
}

export interface EssayLLMAnalytics {
  provider: string;
  model: string;
  evaluation_count: number;
  average_score: number | null;
  malformed_response_dlq_count: number;
  retrigger_count: number;
}

// ── Admin: Results Module (Phase 8) ─────────────────────────────────────────

// pending (no attempt yet) / writing (attempt in progress) / else the
// submission's own 4-bucket pipeline status (EssaySubmissionStatusBucket) —
// see AdminEssayAssignmentResultsView's own docstring (essays/views.py).
export type EssayResultExamStatus = "pending" | "writing" | EssaySubmissionStatusBucket;

export interface EssayResultRow {
  student_user_id: string;
  student_roll_id: string;
  student_name: string;
  department: string;
  set_label: string;
  question_text: string;
  attempt_id: string | null;
  submission_id: string | null;
  exam_status: EssayResultExamStatus;
  submitted_at: string | null;
  score: number | null;
  feedback: { overall: string; breakdown?: Record<string, { score: number; maxScore: number; feedback: string }> } | null;
  evaluated_by: EssayEvaluatedBy | null;
  malpractice_flag: boolean;
  malpractice_reasons: string[];
  plagiarism_flag: boolean;
}

// ── Admin: Analytics Module (Phase 9) ───────────────────────────────────────

export interface EssayScoreDistributionBucket {
  score: number;
  count: number;
}

export interface EssayWordCountVsScorePoint {
  score: number;
  average_word_count: number;
  count: number;
}

export interface EssayWeakestCriterion {
  name: string;
  weak_count: number;
  total_count: number;
  weak_rate_percentage: number;
}

export interface EssayAssignmentAnalytics {
  assignment_id: string;
  generated_at: string;
  total_allocated: number;
  total_submitted: number;
  total_scored: number;
  average_score: number | null;
  score_distribution: EssayScoreDistributionBucket[];
  word_count_vs_score: EssayWordCountVsScorePoint[];
  weakest_criterion: EssayWeakestCriterion | null;
  plagiarism_flag_rate_percentage: number;
  llm_failure_rate_percentage: number;
  metric_definitions: Record<string, string>;
}

// ── Admin: Dashboard Module (Phase 10) ──────────────────────────────────────

export interface EssayThroughputBucket {
  bucket_start: string;
  count: number;
}

export interface EssayAssignmentDashboard {
  assignment_id: string;
  assignment_status: EssayAssignment["status"];
  generated_at: string;
  time_remaining_seconds: number | null;
  total_allocated: number;
  in_progress_count: number;
  total_submitted: number;
  completion_rate_percentage: number;
  total_scored: number;
  average_score: number | null;
  pending_evaluation_count: number;
  dlq_backlog_count: number;
  submission_throughput: EssayThroughputBucket[];
}

// ── Admin: Reports Module (Phase 11) ────────────────────────────────────────
// One table for both generation state (Task 11.1) and delivery state
// (Task 11.2) — see AdminAssignmentReportListView's own docstring
// (essays/views.py) for why these were deliberately not split into two
// endpoints/pages.

export type EssayReportDeliveryStatus = "pending" | "sent" | "bounced" | "complaint";

export interface EssayReportRow {
  submission_id: string;
  student_user_id: string;
  student_roll_id: string;
  student_name: string;
  student_email: string;
  department: string;
  status: EssaySubmissionStatus;
  has_report: boolean;
  score: number | null;
  email_sent_at: string | null;
  delivery_status: EssayReportDeliveryStatus;
  updated_at: string;
}

export interface EssayBulkResendResult {
  dry_run: boolean;
  would_dispatch_count?: number;
  dispatched_count?: number;
  total_matching: number;
  capped: boolean;
  sample?: { submission_id: string; student_email: string }[];
  note?: string;
}

// ── Admin: DLQ Module (Phase 12) ────────────────────────────────────────────
// Platform-wide, not per-assignment or per-institution — EssayFailedJob
// has no institution_id of its own (shared operational infrastructure,
// same as AdminSubmissionsPipelineHealthView's own bare count already
// was). See AdminDLQListView's own docstring (essays/views.py).

export interface EssayDLQEntryRow {
  id: string;
  task_name: string;
  attempts: number;
  dlq_retry_count: number;
  error: string;
  resolved: boolean;
  resolved_at: string | null;
  created_at: string;
}

export interface EssayDLQEntryDetail extends EssayDLQEntryRow {
  task_id: string;
  args: unknown[];
  kwargs: Record<string, unknown>;
  traceback: string;
}

export interface EssayDLQBulkRetryResult {
  dry_run: boolean;
  would_dispatch_count?: number;
  dispatched_count?: number;
  total_matching: number;
  capped: boolean;
  sample?: { id: string; task_name: string; error: string }[];
  note?: string;
}

// ── Admin: Notifications Module (Phase 13) ──────────────────────────────────
// Platform-wide operational alerting, not per-assignment/per-institution
// — same reasoning as the DLQ module above. See
// AdminPipelineHealthSummaryView's own docstring (essays/views.py).

export type EssayAlertTier = "P1" | "P2";

export interface EssayPipelineAlert {
  tier: EssayAlertTier;
  metric: string;
  message: string;
  value: number;
  threshold: number;
}

export interface EssayFailureEvent {
  event_type: string;
  detail: string;
  occurred_at: string;
}

export interface EssayPipelineHealthSummary {
  window_hours: number;
  generated_at: string;
  total_submissions: number;
  completed_submissions: number;
  failed_submissions: number;
  unresolved_dlq_count: number;
  oldest_unresolved_dlq_age_seconds: number | null;
  undispatched_submission_count: number;
  oldest_undispatched_submission_age_seconds: number | null;
  recent_failure_event_count: number;
  recent_failure_events: EssayFailureEvent[];
  alerts: EssayPipelineAlert[];
}
