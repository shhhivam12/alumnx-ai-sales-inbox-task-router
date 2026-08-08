import type {Email} from '../../types'

export function validateEmails(value:unknown):Email[]{
  const payload=Array.isArray(value)?{emails:value}:value as {emails?:unknown}
  if(!payload||!Array.isArray(payload.emails)||!payload.emails.length)throw new Error('JSON must contain at least one email.')
  if(payload.emails.length>250)throw new Error('The browser preview supports at most 250 emails at once.')
  const ids=new Set<string>();const indexes=new Set<string>()
  return payload.emails.map((raw,i)=>{
    const e=raw as Partial<Email>
    for(const key of ['email_id','thread_id','from_name','from_email','to','subject','body','received_at'] as const)if(typeof e[key]!=='string')throw new Error(`Row ${i+1}: ${key} is required.`)
    if(!e.email_id!.trim()||!e.thread_id!.trim())throw new Error(`Row ${i+1}: email_id and thread_id cannot be blank.`)
    if(ids.has(e.email_id!))throw new Error(`Row ${i+1}: duplicate email_id ${e.email_id}.`);ids.add(e.email_id!)
    if(!Number.isInteger(e.message_index)||Number(e.message_index)<0)throw new Error(`Row ${i+1}: message_index must be a non-negative integer.`)
    const indexKey=`${e.thread_id}:${e.message_index}`;if(indexes.has(indexKey))throw new Error(`Row ${i+1}: duplicate thread/message_index.`);indexes.add(indexKey)
    if(!Array.isArray(e.cc)||!Array.isArray(e.attachments)||typeof e.is_reply!=='boolean')throw new Error(`Row ${i+1}: cc, attachments, or is_reply has the wrong type.`)
    if(Number.isNaN(Date.parse(e.received_at!))||!/([zZ]|[+-]\d{2}:\d{2})$/.test(e.received_at!))throw new Error(`Row ${i+1}: received_at must include a timezone.`)
    return e as Email
  })
}

export function chunkEmails(emails:Email[],size:number):Email[][]{
  if(size<1)throw new Error('Chunk size must be positive.')
  const chunks:Email[][]=[];for(let i=0;i<emails.length;i+=size)chunks.push(emails.slice(i,i+size));return chunks
}
