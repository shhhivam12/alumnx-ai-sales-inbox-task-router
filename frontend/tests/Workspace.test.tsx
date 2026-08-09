import {fireEvent,render,screen} from '@testing-library/react'
import {expect,test} from 'vitest'

import {AppHeader} from '../src/components/AppHeader'
import {AppNav} from '../src/components/AppNav'
import {EmailPreviewTable} from '../src/components/EmailPreviewTable'
import {HowItWorks} from '../src/components/HowItWorks'
import {TeamAnalytics} from '../src/components/TeamAnalytics'
import type {Decision,Email,TeamMember} from '../src/types'

const team:TeamMember[]=[{user_id:'u_aarti',name:'Aarti Menon',department:'Sales — Enterprise',scope:'RFPs and tenders'}]

test('shows an explicit cold-start timer',()=>{
  render(<AppHeader config={null} status="waking" wakeSeconds={65}/>)
  expect(screen.getByText(/Render is starting the backend/)).toBeVisible()
  expect(screen.getByText('Waiting 01:05')).toBeVisible()
})

test('navigation exposes inbox, team analytics, and how it works',()=>{
  let selected='inbox'
  const view=render(<AppNav view="inbox" onChange={next=>{selected=next}}/>)
  fireEvent.click(screen.getByRole('button',{name:/Team analytics/}))
  expect(selected).toBe('team')
  view.rerender(<HowItWorks/>)
  expect(screen.getByText('How Alumnx AI routes a sales inbox')).toBeVisible()
})

test('raw preview shows 20 rows per page and supports numbered pages and adjustable size',()=>{
  const emails=Array.from({length:25},(_,index)=>({email_id:`e${index}`,thread_id:`t${index}`,message_index:0,from_name:`Sender ${index}`,from_email:`sender${index}@example.com`,to:'sales@example.com',cc:[],subject:`Subject ${index}`,body:'Message',received_at:'2026-08-09T10:00:00+05:30',attachments:[],is_reply:false})) as Email[]
  render(<EmailPreviewTable emails={emails}/>)
  expect(screen.getByText('Sender 0')).toBeVisible()
  expect(screen.queryByText('Sender 20')).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button',{name:'2'}))
  expect(screen.getByText('Sender 20')).toBeVisible()
  fireEvent.change(screen.getByLabelText('Raw emails rows per page'),{target:{value:'10'}})
  expect(screen.getByText('1–10')).toBeVisible()
})

test('team analytics starts at zero and updates from routed decisions',()=>{
  const {rerender}=render(<TeamAnalytics team={team} decisions={[]} routing={false} complete={false}/>)
  expect(screen.getByText('Waiting for a routed batch')).toBeVisible()
  expect(screen.getAllByText('0').length).toBeGreaterThan(0)
  const decision={email_id:'e1',thread_id:'t1',operation:'create',confidence:.92,reasoning:'RFP',evidence:['RFP'],task:{category:'enterprise_rfp',assignee_id:'u_aarti',priority:'high',due_date:'2026-08-10'}} as Decision
  rerender(<TeamAnalytics team={team} decisions={[decision]} routing={false} complete={true}/>)
  expect(screen.getByText('Current batch complete')).toBeVisible()
  expect(screen.getByText('Needs prompt attention')).toBeVisible()
  expect(screen.getByText(/no open or completed field/i)).toBeVisible()
})
