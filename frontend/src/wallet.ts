// Minimal access to a browser wallet (MetaMask, Rabby, Coinbase Wallet, ...) through the standard
// EIP-1193 provider. TradeLab only asks the wallet for its address and for one signature that
// approves an API wallet. It never sees the wallet's keys and never sends a transaction.

type Eip1193Provider = { request: (args: { method: string; params?: unknown[] }) => Promise<unknown> }

declare global {
  interface Window { ethereum?: Eip1193Provider }
}

export const hasBrowserWallet = (): boolean => typeof window !== 'undefined' && Boolean(window.ethereum)

function provider(): Eip1193Provider {
  if (!window.ethereum) {
    throw new Error('No browser wallet found. Install a wallet such as MetaMask or Rabby, or enter your address instead.')
  }
  return window.ethereum
}

export async function requestWalletAddress(): Promise<string> {
  const accounts = await provider().request({ method: 'eth_requestAccounts' }) as string[] | undefined
  if (!accounts?.length) throw new Error("The wallet didn't share an account.")
  return accounts[0].toLowerCase()
}

export async function getWalletChainId(): Promise<number> {
  return Number.parseInt(await provider().request({ method: 'eth_chainId' }) as string, 16)
}

export async function signTypedData(address: string, typedData: unknown): Promise<string> {
  return await provider().request({ method: 'eth_signTypedData_v4', params: [address, JSON.stringify(typedData)] }) as string
}

// EIP-1193 code 4001: the user rejected the request in their wallet
export const isWalletRejection = (error: unknown): boolean => (error as { code?: number })?.code === 4001
