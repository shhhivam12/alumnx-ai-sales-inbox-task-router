import {expect,test} from '@playwright/test'

const candidate='mahendrushivam123@gmail.com'
const email=(index:number)=>({email_id:`e${index}`,thread_id:`t${index}`,message_index:0,from_name:'Buyer',from_email:'buyer@example.com',to:'sales@example.com',cc:[],subject:`Demo ${index}`,body:'Please arrange a demo.',received_at:'2026-08-09T10:00:00+05:30',attachments:[],is_reply:false})

test('previews 250 emails and routes sequential 100/100/50 chunks',async({page})=>{
  const samples=Array.from({length:250},(_,index)=>email(index));const chunkSizes:number[]=[];let active=0;let maxActive=0
  await page.route('**/api/config',route=>route.fulfill({json:{app_name:'Alumnx AI Sales inbox task router',candidate_id:candidate,max_ingest_emails:100}}))
  await page.route('**/ready',route=>route.fulfill({json:{status:'ready'}}))
  await page.route('**/api/sample-emails?count=250',route=>route.fulfill({json:{emails:samples,count:250}}))
  await page.route('**/ingest',async route=>{active++;maxActive=Math.max(maxActive,active);const body=route.request().postDataJSON();chunkSizes.push(body.emails.length);await new Promise(resolve=>setTimeout(resolve,10));active--;await route.fulfill({json:{run_id:crypto.randomUUID(),processed:body.emails.length,tasks_created:body.emails.length,tasks_updated:0,skipped:0,unchanged:0,errors:[]}})})
  await page.route('**/api/batches/*/decisions',route=>route.fulfill({json:{items:[],total:0}}))
  await page.goto('/')
  await page.getByRole('button',{name:'Load 250 samples'}).click()
  await expect(page.getByText('250 emails · nothing routed yet')).toBeVisible()
  expect(chunkSizes).toEqual([])
  await page.getByRole('button',{name:'Route emails'}).click()
  await expect(page.getByText('250',{exact:true}).first()).toBeVisible()
  expect(chunkSizes).toEqual([100,100,50]);expect(maxActive).toBe(1)
  await expect(page.getByText(candidate)).toBeVisible()
})
