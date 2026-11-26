import { useState, type ReactNode } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  approveApiWallet,
  connectAccount,
  disconnectAccount,
  getConnection,
  prepareApproval,
  removeApiWallet,
  saveApiWalletKey,
  type ConnectionState,
  type Network,
} from '../api/connection'
import { getPortfolio } from '../api/portfolio'
import { getErrorMessage } from '../api/error'
import { useMode } from '../contexts/ModeContext'
import { getWalletChainId, hasBrowserWallet, isWalletRejection, requestWalletAddress, signTypedData } from '../wallet'

const shortAddress = (address?: string | null) => (address ? `${address.slice(0, 6)}…${address.slice(-4)}` : '')
const formatUsd = (value?: number | null) =>
  value == null ? '—' : `$${value.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`

function walletAwareError(error: unknown, fallback: string) {
  return isWalletRejection(error) ? 'Cancelled in your wallet.' : getErrorMessage(error, fallback)
}

export default function SettingsPage() {
  const queryClient = useQueryClient()
  const { mode } = useMode()
  const connectionQuery = useQuery({ queryKey: ['connection'], queryFn: async () => (await getConnection()).data })
  const connection = connectionQuery.data

  // Every change here can change the live balance and whether trading is possible
  const refresh = async (state?: ConnectionState) => {
    if (state) queryClient.setQueryData(['connection'], state)
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ['connection'] }),
      queryClient.invalidateQueries({ queryKey: ['portfolio'] }),
      queryClient.invalidateQueries({ queryKey: ['analytics-overview'] }),
    ])
  }

  const panel = mode === 'paper' ? 'glass-panel' : 'glass-panel-live'

  return (
    <div className="mx-auto max-w-3xl space-y-5">
      <section className={`${panel} space-y-5 p-6 shadow-2xl shadow-black/20`}>
        <div>
          <h2 className="font-display text-lg font-semibold text-white">Hyperliquid account</h2>
          <p className="mt-1 text-sm text-neutral-400">
            Connecting an account syncs your live portfolio from its balance. On its own it&apos;s read-only.
          </p>
        </div>
        {connectionQuery.isLoading ? (
          <p className="text-sm text-neutral-500">Loading…</p>
        ) : connectionQuery.isError || !connection ? (
          <p className="text-sm text-red-400">{getErrorMessage(connectionQuery.error, 'Unable to load connection settings')}</p>
        ) : connection.env_managed ? (
          <EnvManaged connection={connection} />
        ) : connection.account_address ? (
          <ConnectedAccount connection={connection} onChange={refresh} />
        ) : (
          <ConnectAccount onChange={refresh} />
        )}
      </section>

      {connection?.account_address && !connection.env_managed && (
        <section className={`${panel} space-y-5 p-6 shadow-2xl shadow-black/20`}>
          <div>
            <h2 className="font-display text-lg font-semibold text-white">Trading</h2>
            <p className="mt-1 text-sm text-neutral-400">
              TradeLab trades through an <em>API wallet</em>: a separate key that can place and cancel orders on your
              account but can&apos;t withdraw or transfer funds. Your own wallet&apos;s key never leaves your wallet.
            </p>
          </div>
          <Trading connection={connection} onChange={refresh} />
        </section>
      )}
    </div>
  )
}

function EnvManaged({ connection }: { connection: ConnectionState }) {
  return (
    <div className="space-y-3 text-sm">
      <Row label="Account" value={<span className="font-mono">{connection.account_address}</span>} />
      <Row label="Network" value={<NetworkBadge network={connection.network} />} />
      <Row label="Trading" value={connection.trading_enabled ? 'Enabled' : 'Read-only'} />
      <Notice tone="info">
        This connection is set by the HYPERLIQUID_* variables in <code>backend/.env</code>. Remove them and restart
        the backend to manage it here, with the API wallet key kept in your system keychain instead.
      </Notice>
    </div>
  )
}

function ConnectAccount({ onChange }: { onChange: (state?: ConnectionState) => Promise<void> }) {
  const [network, setNetwork] = useState<Network>('mainnet')
  const [address, setAddress] = useState('')

  const connect = useMutation({
    mutationFn: async (source: 'wallet' | 'typed') => {
      const account = source === 'wallet' ? await requestWalletAddress() : address.trim()
      return (await connectAccount(account, network)).data
    },
    onSuccess: (state) => onChange(state),
  })

  return (
    <div className="space-y-5">
      <div className="flex items-center gap-3 text-sm">
        <span className="text-neutral-400">Network</span>
        <div className="flex rounded-lg border border-white/[0.08] bg-black/30 p-1">
          {(['mainnet', 'testnet'] as Network[]).map((item) => (
            <button
              key={item}
              type="button"
              onClick={() => setNetwork(item)}
              className={`rounded-md px-3 py-1.5 text-xs font-medium capitalize ${network === item ? 'bg-white/10 text-white' : 'text-neutral-500 hover:text-neutral-300'}`}
            >
              {item}
            </button>
          ))}
        </div>
      </div>

      {hasBrowserWallet() && (
        <button
          type="button"
          onClick={() => connect.mutate('wallet')}
          disabled={connect.isPending}
          className="w-full rounded-lg border border-green-400/30 bg-green-400/10 px-4 py-3 text-sm font-semibold text-green-400 hover:bg-green-400/15 disabled:opacity-50"
        >
          {connect.isPending ? 'Connecting…' : 'Connect wallet'}
        </button>
      )}

      <form
        onSubmit={(event) => {
          event.preventDefault()
          connect.mutate('typed')
        }}
        className="space-y-2"
      >
        <label htmlFor="account-address" className="block text-xs text-neutral-500">
          {hasBrowserWallet() ? 'Or enter your account address' : 'Account address'}
        </label>
        <div className="flex gap-2">
          <input
            id="account-address"
            value={address}
            onChange={(event) => setAddress(event.target.value)}
            placeholder="0x…"
            spellCheck={false}
            autoComplete="off"
            className="min-w-0 flex-1 rounded-lg border border-white/10 bg-white/[0.025] px-3 py-2.5 font-mono text-sm text-white placeholder-neutral-600 focus:border-white/30 focus:outline-none"
          />
          <button
            type="submit"
            disabled={connect.isPending || !address.trim()}
            className="rounded-lg border border-white/10 px-4 py-2.5 text-sm font-medium text-neutral-200 hover:bg-white/5 disabled:opacity-40"
          >
            Connect
          </button>
        </div>
      </form>

      {connect.isError && <Notice tone="error">{walletAwareError(connect.error, 'Could not connect the account')}</Notice>}
      <p className="text-xs leading-5 text-neutral-500">
        For extra safety, connect a Hyperliquid sub-account that holds only the funds you want TradeLab to trade.
      </p>
    </div>
  )
}

function ConnectedAccount({ connection, onChange }: { connection: ConnectionState; onChange: (state?: ConnectionState) => Promise<void> }) {
  const balanceQuery = useQuery({
    queryKey: ['portfolio', 'live', 'settings'],
    queryFn: async () => (await getPortfolio('live')).data,
    refetchInterval: 10_000,
  })
  const disconnect = useMutation({
    mutationFn: async () => (await disconnectAccount()).data,
    onSuccess: (state) => onChange(state),
  })
  const balance = balanceQuery.data

  return (
    <div className="space-y-4 text-sm">
      <Row label="Account" value={<span className="font-mono" title={connection.account_address ?? ''}>{connection.account_address}</span>} />
      <Row label="Network" value={<NetworkBadge network={connection.network} />} />
      <Row
        label="Account value"
        value={balance?.source === 'hyperliquid' && balance.portfolio_size != null
          ? <span className="tabular-nums">{formatUsd(balance.portfolio_size)}{balance.stale && <span className="ml-2 text-xs text-amber-300">stale</span>}</span>
          : <span className="text-amber-300">{balance?.sync_error ?? 'Checking…'}</span>}
      />
      {balance?.source === 'hyperliquid' && balance.portfolio_size != null && <Row label="Withdrawable" value={<span className="tabular-nums">{formatUsd(balance.withdrawable)}</span>} />}
      <div className="flex justify-end pt-1">
        <button
          type="button"
          onClick={() => {
            if (confirm('Disconnect this account? TradeLab will also delete its API wallet key, and your live portfolio goes back to manual entry.')) {
              disconnect.mutate()
            }
          }}
          disabled={disconnect.isPending}
          className="rounded-lg border border-white/10 px-3 py-2 text-xs text-neutral-300 hover:bg-white/5 disabled:opacity-50"
        >
          Disconnect
        </button>
      </div>
      {disconnect.isError && <Notice tone="error">{getErrorMessage(disconnect.error, 'Could not disconnect')}</Notice>}
    </div>
  )
}

function Trading({ connection, onChange }: { connection: ConnectionState; onChange: (state?: ConnectionState) => Promise<void> }) {
  const [showKeyForm, setShowKeyForm] = useState(false)
  const [privateKey, setPrivateKey] = useState('')
  const [walletStep, setWalletStep] = useState<string | null>(null)

  const enable = useMutation({
    mutationFn: async () => {
      setWalletStep('Connecting to your wallet…')
      const walletAddress = await requestWalletAddress()
      const chainId = await getWalletChainId()
      const { data: prepared } = await prepareApproval(chainId)
      if (walletAddress !== prepared.signer) {
        throw new Error(
          `Your wallet is on ${shortAddress(walletAddress)}, but the approval must come from ${prepared.signer}` +
          (prepared.signer !== connection.account_address ? ' (this sub-account\'s main account)' : '') +
          '. Switch accounts in your wallet and try again.',
        )
      }
      setWalletStep('Approve the TradeLab API wallet in your wallet…')
      const signature = await signTypedData(prepared.signer, prepared.typed_data)
      setWalletStep('Registering the API wallet with Hyperliquid…')
      return (await approveApiWallet(prepared.nonce, signature)).data
    },
    onSuccess: (state) => onChange(state),
    onSettled: () => setWalletStep(null),
  })

  const saveKey = useMutation({
    mutationFn: async () => (await saveApiWalletKey(privateKey)).data,
    onSuccess: async (state) => {
      setPrivateKey('')
      setShowKeyForm(false)
      await onChange(state)
    },
  })

  const disable = useMutation({
    mutationFn: async () => (await removeApiWallet()).data,
    onSuccess: (state) => onChange(state),
  })

  if (connection.trading_enabled) {
    return (
      <div className="space-y-4 text-sm">
        <Row label="Status" value={<span className="font-medium text-green-400">Trading enabled</span>} />
        <Row label="API wallet" value={<span className="font-mono">{connection.api_wallet_address}</span>} />
        <Notice tone="info">
          The API wallet&apos;s key is stored in your system keychain. Disabling trading deletes it from this computer. To
          revoke it on Hyperliquid too, remove it under More → API on app.hyperliquid.xyz.
        </Notice>
        <div className="flex justify-end">
          <button
            type="button"
            onClick={() => disable.mutate()}
            disabled={disable.isPending}
            className="rounded-lg border border-red-400/30 bg-red-400/[0.06] px-3 py-2 text-xs font-medium text-red-300 hover:bg-red-400/10 disabled:opacity-50"
          >
            Disable trading
          </button>
        </div>
        {disable.isError && <Notice tone="error">{getErrorMessage(disable.error, 'Could not disable trading')}</Notice>}
      </div>
    )
  }

  if (!connection.keychain_available) {
    return (
      <Notice tone="error">
        No system keychain is available on this computer, so TradeLab can&apos;t store an API wallet key safely. On a
        machine without one, set the HYPERLIQUID_* variables in <code>backend/.env</code> instead.
      </Notice>
    )
  }

  return (
    <div className="space-y-5 text-sm">
      <Row label="Status" value={<span className="text-neutral-300">Read-only</span>} />
      {hasBrowserWallet() ? (
        <div className="space-y-2">
          <button
            type="button"
            onClick={() => enable.mutate()}
            disabled={enable.isPending}
            className="w-full rounded-lg border border-green-400/30 bg-green-400/10 px-4 py-3 text-sm font-semibold text-green-400 hover:bg-green-400/15 disabled:opacity-50"
          >
            {enable.isPending ? walletStep ?? 'Working…' : 'Enable trading'}
          </button>
          <p className="text-xs leading-5 text-neutral-500">
            Your wallet asks you to sign one message approving a new &ldquo;TradeLab&rdquo; API wallet. It&apos;s free: no
            gas and no transaction.
          </p>
        </div>
      ) : (
        <Notice tone="info">Install a browser wallet such as MetaMask or Rabby to enable trading with one signature, or use an API wallet key below.</Notice>
      )}
      {enable.isError && <Notice tone="error">{walletAwareError(enable.error, 'Could not enable trading')}</Notice>}

      <div className="border-t border-white/[0.06] pt-4">
        <button type="button" onClick={() => setShowKeyForm((value) => !value)} className="text-xs text-neutral-400 underline underline-offset-4 hover:text-white">
          {showKeyForm ? 'Hide' : 'Use an existing API wallet key instead'}
        </button>
        {showKeyForm && (
          <form
            onSubmit={(event) => {
              event.preventDefault()
              saveKey.mutate()
            }}
            className="mt-3 space-y-2"
          >
            <p className="text-xs leading-5 text-neutral-500">
              Create an API wallet on Hyperliquid (More → API), approve it, and paste its private key here.{' '}
              <span className="text-amber-300">Never paste your main wallet&apos;s key</span>: it can withdraw funds, and
              TradeLab will refuse it.
            </p>
            <div className="flex gap-2">
              <input
                type="password"
                value={privateKey}
                onChange={(event) => setPrivateKey(event.target.value)}
                placeholder="API wallet private key"
                autoComplete="off"
                spellCheck={false}
                className="min-w-0 flex-1 rounded-lg border border-white/10 bg-white/[0.025] px-3 py-2.5 font-mono text-sm text-white placeholder-neutral-600 focus:border-white/30 focus:outline-none"
              />
              <button
                type="submit"
                disabled={saveKey.isPending || !privateKey.trim()}
                className="rounded-lg border border-white/10 px-4 py-2.5 text-sm font-medium text-neutral-200 hover:bg-white/5 disabled:opacity-40"
              >
                {saveKey.isPending ? 'Checking…' : 'Save'}
              </button>
            </div>
            {saveKey.isError && <Notice tone="error">{getErrorMessage(saveKey.error, 'Could not save the key')}</Notice>}
          </form>
        )}
      </div>
    </div>
  )
}

function Row({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-4">
      <span className="text-neutral-500">{label}</span>
      <span className="min-w-0 truncate text-right text-neutral-200">{value}</span>
    </div>
  )
}

function NetworkBadge({ network }: { network: Network }) {
  return (
    <span className={`rounded-full px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wider ${network === 'testnet' ? 'bg-amber-400/10 text-amber-300' : 'bg-green-400/10 text-green-400'}`}>
      {network}
    </span>
  )
}

function Notice({ tone, children }: { tone: 'info' | 'error'; children: ReactNode }) {
  return (
    <p className={`rounded-lg border px-3 py-2 text-xs leading-5 ${tone === 'error' ? 'border-red-400/20 bg-red-400/[0.06] text-red-300' : 'border-white/[0.07] bg-white/[0.02] text-neutral-400'}`}>
      {children}
    </p>
  )
}
