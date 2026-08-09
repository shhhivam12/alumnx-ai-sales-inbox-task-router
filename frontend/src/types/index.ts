export type Email = {email_id:string;thread_id:string;message_index:number;from_name:string;from_email:string;to:string;cc:string[];subject:string;body:string;received_at:string;attachments:string[];is_reply:boolean;[key:string]:unknown}
export type Config = {app_name:string;candidate_id:string;max_ingest_emails:number}
export type IngestResult = {run_id:string;processed:number;tasks_created:number;tasks_updated:number;skipped:number;unchanged:number;errors:Array<Record<string,unknown>>}
export type Decision = {email_id:string;thread_id:string;operation:string;original_operation?:string;delivery_outcome?:string;skip_reason?:string;confidence:number;reasoning:string;evidence:string[];task?:{category:string;assignee_id:string;priority:string;company_name?:string;due_date?:string;deal_value_inr?:number}}
export type TeamMember = {user_id:string;name:string;department:string;scope:string}
export type ChatScope = {type:'all'}|{type:'batch';id:string}
export type ChatResponse = {answer:string;supporting_data:Record<string,unknown>;scope:ChatScope}
