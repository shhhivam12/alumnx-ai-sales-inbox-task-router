import {describe,expect,test} from 'vitest'
import {chunkEmails,validateEmails} from '../src/features/input/validation'
import type {Email} from '../src/types'

const email=(index:number):Email=>({email_id:`e${index}`,thread_id:`t${index}`,message_index:0,from_name:'Buyer',from_email:'buyer@example.com',to:'sales@example.com',cc:[],subject:'Demo',body:'Please send a demo',received_at:'2026-08-09T10:00:00+05:30',attachments:[],is_reply:false})

describe('input contract',()=>{
  test('accepts both raw arrays and full payloads',()=>{
    expect(validateEmails([email(1)])).toHaveLength(1)
    expect(validateEmails({candidate_id:'ignored-in-browser',emails:[email(2)]})).toHaveLength(1)
  })
  test('250 emails become sequential-size chunks of 100, 100, and 50',()=>{
    expect(chunkEmails(Array.from({length:250},(_,i)=>email(i)),100).map(chunk=>chunk.length)).toEqual([100,100,50])
  })
  test('rejects duplicate identities before ingestion',()=>{
    expect(()=>validateEmails([email(1),email(1)])).toThrow(/duplicate email_id/)
  })
})
