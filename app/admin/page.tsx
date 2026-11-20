"use client";

import { useCallback, useEffect, useState, type ReactNode } from "react";
import { useRouter } from "next/navigation";
import {
  ArrowLeft,
  Clock,
  Gauge,
  RefreshCw,
  RotateCw,
  ShieldCheck,
  ShieldX,
  UserCheck,
  UserX,
} from "lucide-react";
import { AuthGuard } from "@/lib/components/auth/AuthGuard";
import { useAuth } from "@/lib/auth-context";
import { apiClient } from "@/lib/api";

interface AdminUser {
  uid: string;
  email: string;
  name: string;
  verified: boolean;
  role: string;
  last_login: string;
}

interface ZeroGpuQuota {
  total_gpu_seconds: number;
  remaining_gpu_seconds: number;
  used_gpu_seconds: number;
  remaining_percent: number;
  resets_at: string | null;
  overquota_used_gpu_seconds: number;
  checked_at: string;
}

export default function AdminPage() {
  const { isAdmin, verificationLoaded } = useAuth();
  const router = useRouter();
  const [pending, setPending] = useState<AdminUser[]>([]);
  const [approved, setApproved] = useState<AdminUser[]>([]);
  const [loadingUsers, setLoadingUsers] = useState(true);
  const [busyUid, setBusyUid] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [quota, setQuota] = useState<ZeroGpuQuota | null>(null);
  const [loadingQuota, setLoadingQuota] = useState(true);
  const [quotaError, setQuotaError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [p, a] = await Promise.all([
        apiClient.get<AdminUser[]>("/api/admin/users", { params: { status: "pending" } }),
        apiClient.get<AdminUser[]>("/api/admin/users", { params: { status: "approved" } }),
      ]);
      setPending(p.data ?? []);
      setApproved(a.data ?? []);
      setError(null);
    } catch (err) {
      console.error("Admin list failed:", err);
      setError("Gagal memuat daftar user.");
    } finally {
      setLoadingUsers(false);
    }
  }, []);

  const loadQuota = useCallback(async () => {
    setLoadingQuota(true);
    try {
      const response = await apiClient.get<ZeroGpuQuota>("/api/admin/zero-gpu/quota");
      setQuota(response.data);
      setQuotaError(null);
    } catch (err: unknown) {
      console.error("ZeroGPU quota failed:", err);
      const detail =
        typeof err === "object" && err !== null && "response" in err
          ? (err as { response?: { data?: { detail?: unknown } } }).response?.data?.detail
          : null;
      setQuotaError(
        typeof detail === "string" ? detail : "Gagal memuat kuota ZeroGPU Hugging Face."
      );
    } finally {
      setLoadingQuota(false);
    }
  }, []);

  useEffect(() => {
    if (verificationLoaded && !isAdmin) {
      router.replace("/chat");
      return;
    }
    if (verificationLoaded && isAdmin) {
      const timer = window.setTimeout(() => {
        void load();
        void loadQuota();
      }, 0);
      const quotaTimer = window.setInterval(() => void loadQuota(), 60_000);
      return () => {
        window.clearTimeout(timer);
        window.clearInterval(quotaTimer);
      };
    }
  }, [verificationLoaded, isAdmin, router, load, loadQuota]);

  const setVerified = async (uid: string, verified: boolean) => {
    setBusyUid(uid);
    setError(null);
    try {
      await apiClient.post(`/api/admin/users/${uid}/${verified ? "approve" : "revoke"}`);
      await load();
    } catch (err) {
      console.error("Admin status change failed:", err);
      setError("Gagal mengubah status user.");
    } finally {
      setBusyUid(null);
    }
  };

  if (!verificationLoaded || !isAdmin) {
    return null;
  }

  return (
    <AuthGuard>
      <div className="min-h-screen bg-[#F5F5F7]">
        <header className="border-b border-zinc-200 bg-white/80 backdrop-blur">
          <div className="mx-auto flex max-w-4xl items-center justify-between gap-3 px-4 py-3.5 sm:px-6">
            <div className="flex min-w-0 items-center gap-3">
              <button
                type="button"
                onClick={() => router.push("/chat")}
                className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-zinc-100 text-zinc-600 transition-colors hover:bg-zinc-200"
                aria-label="Kembali ke chat"
              >
                <ArrowLeft className="h-4 w-4" />
              </button>
              <div className="min-w-0">
                <h1 className="truncate text-base font-bold text-zinc-900">
                  Admin — Verifikasi User
                </h1>
                <p className="truncate text-xs text-zinc-500">
                  Setujui atau cabut akses user yang terdaftar
                </p>
              </div>
            </div>
            <button
              type="button"
              onClick={() => {
                void load();
                void loadQuota();
              }}
              className="flex shrink-0 items-center gap-1.5 rounded-full border border-zinc-200 bg-white px-3 py-1.5 text-xs font-semibold text-zinc-600 transition-colors hover:bg-zinc-50"
            >
              <RefreshCw className="h-3.5 w-3.5" />
              Refresh
            </button>
          </div>
        </header>

        <main className="mx-auto max-w-4xl space-y-6 px-4 py-6 sm:px-6">
          <ZeroGpuQuotaCard
            quota={quota}
            loading={loadingQuota}
            error={quotaError}
            onRefresh={() => void loadQuota()}
          />

          {error && (
            <div className="rounded-xl bg-red-50 px-4 py-3 text-sm font-medium text-red-600 ring-1 ring-red-100">
              {error}
            </div>
          )}

          {loadingUsers ? (
            <div className="flex items-center gap-2 py-16 text-zinc-400">
              <RotateCw className="h-5 w-5 animate-spin" />
              <span className="text-sm">Memuat daftar user...</span>
            </div>
          ) : (
            <>
              <section>
                <div className="mb-3 flex items-center gap-2">
                  <ShieldX className="h-4 w-4 text-amber-500" />
                  <h2 className="text-sm font-bold text-zinc-800">
                    Menunggu Persetujuan ({pending.length})
                  </h2>
                </div>
                {pending.length === 0 ? (
                  <p className="rounded-xl border border-dashed border-zinc-300 bg-white px-4 py-6 text-center text-sm text-zinc-400">
                    Tidak ada user yang menunggu persetujuan.

                  </p>
                ) : (
                  <div className="space-y-2">
                    {pending.map((user) => (
                      <UserRow
                        key={user.uid}
                        user={user}
                        busy={busyUid === user.uid}
                        actionLabel="Approve"
                        actionIcon={<UserCheck className="h-3.5 w-3.5" />}
                        onAction={() => void setVerified(user.uid, true)}
                      />
                    ))}
                  </div>
                )}
              </section>

              <section>
                <div className="mb-3 flex items-center gap-2">
                  <ShieldCheck className="h-4 w-4 text-emerald-500" />
                  <h2 className="text-sm font-bold text-zinc-800">
                    Disetujui ({approved.length})
                  </h2>
                </div>
                {approved.length === 0 ? (
                  <p className="rounded-xl border border-dashed border-zinc-300 bg-white px-4 py-6 text-center text-sm text-zinc-400">
                    Belum ada user yang disetujui.



                  </p>
                ) : (
                  <div className="space-y-2">
                    {approved.map((user) => (
                      <UserRow
                        key={user.uid}
                        user={user}
                        busy={busyUid === user.uid}
                        actionLabel="Revoke"
                        actionIcon={<UserX className="h-3.5 w-3.5" />}
                        onAction={() => void setVerified(user.uid, false)}
                        danger
                      />
                    ))}
                  </div>
                )}
              </section>
            </>
          )}
        </main>
      </div>
    </AuthGuard>
  );
}

function ZeroGpuQuotaCard({
  quota,
  loading,
  error,
  onRefresh,
}: {
  quota: ZeroGpuQuota | null;
  loading: boolean;
  error: string | null;
  onRefresh: () => void;
}) {
  const percent = Math.max(0, Math.min(100, quota?.remaining_percent ?? 0));
  const status = percent > 50 ? "safe" : percent > 20 ? "warning" : "critical";
  const colors = {
    safe: { bar: "bg-emerald-500", text: "text-emerald-700", badge: "bg-emerald-50" },
    warning: { bar: "bg-amber-500", text: "text-amber-700", badge: "bg-amber-50" },
    critical: { bar: "bg-red-500", text: "text-red-700", badge: "bg-red-50" },
  }[status];
  const remainingMinutes = quota ? quota.remaining_gpu_seconds / 60 : 0;
  const resetAt = quota?.resets_at
    ? new Intl.DateTimeFormat("id-ID", {
        dateStyle: "medium",
        timeStyle: "short",
        timeZone: "Asia/Jakarta",
      }).format(new Date(quota.resets_at))
    : "Belum dijadwalkan";
  const checkedAt = quota
    ? new Intl.DateTimeFormat("id-ID", {
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
        timeZone: "Asia/Jakarta",
      }).format(new Date(quota.checked_at))
    : null;

  return (
    <section className="overflow-hidden rounded-2xl border border-zinc-200 bg-white shadow-sm">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-zinc-100 px-5 py-4">
        <div className="flex items-center gap-3">
          <div className="grid h-10 w-10 place-items-center rounded-xl bg-purple-50 text-purple-700">
            <Gauge className="h-5 w-5" />
          </div>
          <div>
            <h2 className="text-sm font-bold text-zinc-900">Kuota Hugging Face ZeroGPU</h2>
            <p className="text-xs text-zinc-500">Token bersama backend Legal-Verse</p>
          </div>
        </div>
        <button
          type="button"
          onClick={onRefresh}
          disabled={loading}
          className="flex items-center gap-1.5 rounded-full border border-zinc-200 px-3 py-1.5 text-xs font-semibold text-zinc-600 hover:bg-zinc-50 disabled:opacity-50"
        >
          <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
          Perbarui kuota
        </button>
      </div>

      <div className="p-5">
        {loading && !quota ? (
          <div className="flex items-center gap-2 py-6 text-sm text-zinc-400">
            <RotateCw className="h-4 w-4 animate-spin" />
            Memeriksa kuota ZeroGPU...
          </div>
        ) : error && !quota ? (
          <div className="rounded-xl bg-red-50 px-4 py-3 text-sm font-medium text-red-700">
            {error}
          </div>
        ) : quota ? (
          <>
            <div className="flex items-end justify-between gap-4">
              <div>
                <div className="text-3xl font-extrabold tracking-tight text-zinc-900">
                  {remainingMinutes.toLocaleString("id-ID", { maximumFractionDigits: 1 })}
                  <span className="ml-1 text-base font-semibold text-zinc-500">menit tersisa</span>
                </div>
                <p className="mt-1 text-xs text-zinc-500">
                  {quota.remaining_gpu_seconds.toLocaleString("id-ID", { maximumFractionDigits: 0 })}
                  {" / "}
                  {quota.total_gpu_seconds.toLocaleString("id-ID", { maximumFractionDigits: 0 })}
                  {" GPU-detik"}
                </p>
              </div>
              <span className={`rounded-full px-3 py-1 text-xs font-bold ${colors.badge} ${colors.text}`}>
                {percent.toLocaleString("id-ID", { maximumFractionDigits: 1 })}%
              </span>
            </div>

            <div className="mt-4 h-2.5 overflow-hidden rounded-full bg-zinc-100">
              <div
                className={`h-full rounded-full transition-[width] duration-500 ${colors.bar}`}
                style={{ width: `${percent}%` }}
              />
            </div>

            <div className="mt-5 grid gap-3 sm:grid-cols-3">
              <QuotaInfo label="Terpakai" value={`${(quota.used_gpu_seconds / 60).toLocaleString("id-ID", { maximumFractionDigits: 1 })} menit`} />
              <QuotaInfo label="Kredit tambahan" value={`${(quota.overquota_used_gpu_seconds / 60).toLocaleString("id-ID", { maximumFractionDigits: 1 })} menit`} />
              <QuotaInfo label="Reset kuota" value={`${resetAt} WIB`} icon={<Clock className="h-3.5 w-3.5" />} />
            </div>

            <div className="mt-4 rounded-xl bg-purple-50 px-4 py-3 text-xs leading-relaxed text-purple-900">
              Request Output 32K memesan sekitar <strong>1.069 GPU-detik</strong>. Jika sisa kuota
              berada di bawah angka tersebut, request dapat ditolak sebelum inferensi dimulai.
            </div>

            <p className="mt-3 text-[11px] text-zinc-400">
              Diperiksa {checkedAt} WIB · diperbarui otomatis setiap 60 detik
              {error ? ` · Pembaruan terakhir gagal: ${error}` : ""}
            </p>
          </>
        ) : null}
      </div>
    </section>
  );
}

function QuotaInfo({ label, value, icon }: { label: string; value: string; icon?: ReactNode }) {
  return (
    <div className="rounded-xl bg-zinc-50 px-3.5 py-3">
      <div className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wide text-zinc-400">
        {icon}
        {label}
      </div>
      <div className="mt-1 text-sm font-bold text-zinc-700">{value}</div>
    </div>
  );
}

function UserRow({
  user,
  busy,
  actionLabel,
  actionIcon,
  onAction,
  danger,
}: {
  user: AdminUser;
  busy: boolean;
  actionLabel: string;
  actionIcon: ReactNode;
  onAction: () => void;
  danger?: boolean;
}) {
  return (
    <div className="flex items-center gap-3 rounded-xl border border-zinc-200 bg-white px-4 py-3">
      <div className="min-w-0 flex-1">
        <div className="truncate text-sm font-semibold text-zinc-800">
          {user.name || user.email || "Tanpa nama"}
        </div>
        <div className="truncate text-xs text-zinc-500">{user.email || user.uid}</div>
        {user.last_login && (
          <div className="mt-0.5 text-[11px] text-zinc-400">
            Login terakhir: {new Date(user.last_login).toLocaleString("id-ID")}
          </div>
        )}
      </div>
      {user.role === "admin" && (
        <span className="shrink-0 rounded-full bg-purple-100 px-2.5 py-1 text-[10px] font-bold text-purple-700">
          ADMIN
        </span>
      )}
      <button
        type="button"
        onClick={onAction}
        disabled={busy}
        className={`flex shrink-0 items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-semibold transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${
          danger
            ? "bg-red-50 text-red-600 hover:bg-red-100"
            : "bg-emerald-50 text-emerald-700 hover:bg-emerald-100"
        }`}
      >
        {actionIcon}
        {actionLabel}
      </button>
    </div>
  );
}
