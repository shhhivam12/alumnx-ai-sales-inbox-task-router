import {render,screen} from '@testing-library/react'
import {expect,test} from 'vitest'
import {DecisionTable} from '../src/components/DecisionTable'
import type {Decision} from '../src/types'

test('shows the original route for an unchanged replay delivery',() => {
  const replayed = {
    email_id:'replayed-email',
    thread_id:'replayed-thread',
    operation:'create',
    original_operation:'create',
    delivery_outcome:'unchanged',
    confidence:0.84,
    reasoning:'Previously classified as a product enquiry.',
    evidence:['product demo'],
    task:{category:'smb_enquiry',assignee_id:'u_rohit',priority:'medium'},
  } as Decision & {original_operation:string;delivery_outcome:string}
  render(<DecisionTable items={[replayed]}/>)
  expect(screen.getByText('Every routing decision')).toBeInTheDocument()
  expect(screen.getByText('unchanged')).toBeInTheDocument()
  expect(screen.getByText('Original: create')).toBeInTheDocument()
  expect(screen.getByText('smb_enquiry')).toBeInTheDocument()
})
