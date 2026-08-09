import {render,screen} from '@testing-library/react'
import {expect,test} from 'vitest'

import {OperationsDashboard} from '../src/components/OperationsDashboard'
import type {Decision,Email,TeamMember} from '../src/types'

const team:TeamMember[]=[{user_id:'u_aarti',name:'Aarti Menon',department:'Sales — Enterprise',scope:'RFPs and tenders'}]
const emails=Array.from({length:5},(_,i)=>({email_id:`e${i}`,thread_id:`t${i}`,message_index:0,from_name:`Buyer ${i}`,from_email:`buyer${i}@example.com`,to:'sales@example.com',cc:[],subject:`RFP ${i}`,body:'Please respond.',received_at:'2026-08-09T10:00:00+05:30',attachments:[],is_reply:false})) as Email[]
const decisions=emails.map((email,i)=>({email_id:email.email_id,thread_id:email.thread_id,operation:'create',confidence:.92,reasoning:'Formal RFP.',evidence:['RFP'],task:{category:'enterprise_rfp',assignee_id:'u_aarti',priority:i<2?'high':'medium',company_name:`Company ${i}`,due_date:i<2?'2026-08-10':undefined,deal_value_inr:1000000}})) as Decision[]

test('shows grounded persona load, deadline pressure, value, and concentration warning',()=>{
  render(<OperationsDashboard emails={emails} decisions={decisions} results={[{run_id:'r1',processed:5,tasks_created:5,tasks_updated:0,skipped:0,unchanged:0,errors:[]}]} team={team} routing={false} complete={true}/>)
  expect(screen.getByText('Live routing dashboard')).toBeVisible()
  expect(screen.getByText('Aarti Menon')).toBeVisible()
  expect(screen.getByText(/Load watch · 100%/)).toBeVisible()
  expect(screen.getByText('₹50,00,000')).toBeVisible()
  expect(screen.getByText('2 with dated deadlines')).toBeVisible()
  expect(screen.getByText('Batch complete')).toBeVisible()
})
