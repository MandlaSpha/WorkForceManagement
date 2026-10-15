import { api, unwrap } from '@/shared/api'

import type { ContractChange, ContractRow, Customer, NewContract } from '../model/types'

export async function fetchContracts(): Promise<ContractRow[]> {
  return unwrap(await api.GET('/api/v1/contracts', { params: { query: {} } }))
}

export async function fetchCustomers(): Promise<Customer[]> {
  return unwrap(await api.GET('/api/v1/contracts/customers'))
}

export async function createCustomer(name: string): Promise<Customer> {
  return unwrap(await api.POST('/api/v1/contracts/customers', { body: { name } }))
}

export async function createContract(body: NewContract): Promise<ContractRow> {
  return unwrap(await api.POST('/api/v1/contracts', { body }))
}

export async function updateContract(id: number, body: ContractChange): Promise<ContractRow> {
  return unwrap(
    await api.PUT('/api/v1/contracts/{contract_id}', {
      params: { path: { contract_id: id } },
      body,
    }),
  )
}
