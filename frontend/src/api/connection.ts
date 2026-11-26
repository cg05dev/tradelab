import api from './client'

export type Network = 'mainnet' | 'testnet'

export type ConnectionState = {
  source: 'none' | 'settings' | 'env'
  env_managed: boolean
  network: Network
  account_address: string | null
  trading_enabled: boolean
  api_wallet_address: string | null
  keychain_available: boolean
}

export type PreparedApproval = {
  nonce: number
  typed_data: Record<string, unknown>
  signer: string
  api_wallet_address: string
}

export const getConnection = () => api.get<ConnectionState>('/api/connection')
export const connectAccount = (accountAddress: string, network: Network) =>
  api.put<ConnectionState>('/api/connection', { account_address: accountAddress, network })
export const disconnectAccount = () => api.delete<ConnectionState>('/api/connection')
export const saveApiWalletKey = (privateKey: string) =>
  api.post<ConnectionState>('/api/connection/api-wallet', { private_key: privateKey })
export const removeApiWallet = () => api.delete<ConnectionState>('/api/connection/api-wallet')
export const prepareApproval = (chainId: number) =>
  api.post<PreparedApproval>('/api/connection/api-wallet/prepare', { chain_id: chainId })
export const approveApiWallet = (nonce: number, signature: string) =>
  api.post<ConnectionState>('/api/connection/api-wallet/approve', { nonce, signature })
