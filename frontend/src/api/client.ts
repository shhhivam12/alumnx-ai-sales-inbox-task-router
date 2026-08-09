import type {Config,Email,IngestResult,Decision,ChatResponse,ChatScope,TeamMember} from '../types'

const API_BASE_URL=(import.meta.env.VITE_API_BASE_URL||'').replace(/\/+$/,'')

async function request<T>(path:string, init?:RequestInit):Promise<T>{const response=await fetch(`${API_BASE_URL}${path}`,init);const data=await response.json().catch(()=>({}));if(!response.ok)throw new Error(data?.error?.message||`Request failed (${response.status})`);return data}
export const getConfig=()=>request<Config>('/api/config')
export const getReady=()=>request<{status:string}>('/ready')
export const getUsers=()=>request<{team:TeamMember[]}>('/users')
export const getSamples=(count=250)=>request<{emails:Email[]}>(`/api/sample-emails?count=${count}`)
export const ingest=(candidate_id:string,client_batch_id:string,emails:Email[])=>request<IngestResult>('/ingest',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({candidate_id,client_batch_id,source:'generated',emails}),signal:AbortSignal.timeout(16*60*1000)})
export const getDecisions=(batch:string)=>request<{items:Decision[]}>(`/api/batches/${batch}/decisions`)
export const sendChat=(candidate_id:string,query:string,scope:ChatScope)=>request<ChatResponse>('/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({candidate_id,query,scope})})
export const sendFeedback=(emailId:string,label:string,note?:string)=>request(`/api/decisions/${encodeURIComponent(emailId)}/feedback`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({label,note})})
