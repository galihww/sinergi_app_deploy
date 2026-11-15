"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import {
  CheckCircle2,
  ChevronUp,
  KeyRound,
  LoaderCircle,
  LogOut,
  Pencil,
  X,
} from "lucide-react";
import { translateFirebaseError, useAuth } from "@/lib/auth-context";

type UserAccountMenuProps = {
  isCollapsed: boolean;
};

export function UserAccountMenu({ isCollapsed }: UserAccountMenuProps) {
  const router = useRouter();
  const {
    user,
    loading,
    logout,
    updateDisplayName,
    requestPasswordReset,
  } = useAuth();
  const [isOpen, setIsOpen] = useState(false);
  const [isEditing, setIsEditing] = useState(false);
  const [name, setName] = useState("");
  const [isSaving, setIsSaving] = useState(false);
  const [isResetting, setIsResetting] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  const displayName = user?.displayName ?? user?.email ?? "User";
  const initials = (displayName.charAt(0) || "U").toUpperCase();

  useEffect(() => {
    const closeMenu = (event: MouseEvent) => {
      if (!containerRef.current?.contains(event.target as Node)) {
        setIsOpen(false);
      }
    };
    document.addEventListener("mousedown", closeMenu);
    return () => document.removeEventListener("mousedown", closeMenu);
  }, []);

  const openEditor = () => {
    setName(user?.displayName ?? "");
    setError(null);
    setMessage(null);
    setIsOpen(false);
    setIsEditing(true);
  };

  const handleSave = async (event: FormEvent) => {
    event.preventDefault();
    if (!name.trim()) {
      setError("Nama tidak boleh kosong.");
      return;
    }

    setIsSaving(true);
    setError(null);
    try {
      await updateDisplayName(name);
      setIsEditing(false);
      setMessage("Profil berhasil diperbarui.");
    } catch (err) {
      setError(translateFirebaseError(err));
    } finally {
      setIsSaving(false);
    }
  };

  const handlePasswordReset = async () => {
    setIsResetting(true);
    setError(null);
    setMessage(null);
    try {
      await requestPasswordReset();
      setMessage(`Tautan reset password dikirim ke ${user?.email ?? "email Anda"}.`);
      setIsOpen(false);
    } catch (err) {
      setError(translateFirebaseError(err));
    } finally {
      setIsResetting(false);
    }
  };

  const handleLogout = async () => {
    await logout();
    router.push("/");
  };

  return (
    <>
      <div
        ref={containerRef}
        className="relative mt-auto border-t border-white/10 px-3 py-3"
      >
        {message && !isOpen && (
          <div className="mb-2 flex gap-2 rounded-xl bg-emerald-400/15 px-3 py-2 text-[11px] leading-relaxed text-emerald-100">
            <CheckCircle2 className="mt-0.5 h-3.5 w-3.5 shrink-0" />
            {!isCollapsed && <span>{message}</span>}
          </div>
        )}

        {isOpen && (
          <div
            className={`absolute bottom-[calc(100%+8px)] z-50 overflow-hidden rounded-2xl border border-white/10 bg-[#2A2238] p-1.5 shadow-2xl ${
              isCollapsed ? "left-2 w-52" : "left-3 right-3"
            }`}
          >
            <button
              type="button"
              onClick={openEditor}
              className="flex w-full items-center gap-2.5 rounded-xl px-3 py-2.5 text-left text-sm text-white/80 transition-colors hover:bg-white/10 hover:text-white"
            >
              <Pencil className="h-4 w-4 text-pink-300" />
              Edit profil
            </button>
            <button
              type="button"
              onClick={() => void handlePasswordReset()}
              disabled={isResetting}
              className="flex w-full items-center gap-2.5 rounded-xl px-3 py-2.5 text-left text-sm text-white/80 transition-colors hover:bg-white/10 hover:text-white disabled:opacity-60"
            >
              {isResetting ? (
                <LoaderCircle className="h-4 w-4 animate-spin text-pink-300" />
              ) : (
                <KeyRound className="h-4 w-4 text-pink-300" />
              )}
              Reset password
            </button>
            <div className="my-1 h-px bg-white/10" />
            <button
              type="button"
              onClick={() => void handleLogout()}
              disabled={loading}
              className="flex w-full items-center gap-2.5 rounded-xl px-3 py-2.5 text-left text-sm text-red-200 transition-colors hover:bg-red-400/10 hover:text-red-100 disabled:opacity-60"
            >
              <LogOut className="h-4 w-4" />
              Log out
            </button>
          </div>
        )}

        <button
          type="button"
          onClick={() => {
            setIsOpen((open) => !open);
            setMessage(null);
            setError(null);
          }}
          aria-expanded={isOpen}
          aria-label="Buka menu akun"
          className={`flex w-full items-center rounded-xl p-1.5 text-left transition-colors hover:bg-white/10 ${
            isCollapsed ? "justify-center" : "gap-3"
          }`}
        >
          {user?.photoURL ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={user.photoURL}
              alt="Profil"
              referrerPolicy="no-referrer"
              className="h-9 w-9 shrink-0 rounded-full object-cover"
            />
          ) : (
            <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-pink-400 text-sm font-bold text-[#1A1625]">
              {initials}
            </span>
          )}
          {!isCollapsed && (
            <>
              <span className="min-w-0 flex-1">
                <span className="block truncate text-sm font-semibold">{displayName}</span>
                <span className="mt-0.5 block truncate text-[10px] text-white/50">
                  {user?.email}
                </span>
              </span>
              <ChevronUp
                className={`h-4 w-4 shrink-0 text-white/50 transition-transform ${
                  isOpen ? "rotate-180" : ""
                }`}
              />
            </>
          )}
        </button>
        {error && !isEditing && (
          <p className="mt-2 rounded-lg bg-red-400/15 px-2.5 py-2 text-[11px] text-red-100">
            {error}
          </p>
        )}
      </div>

      {isEditing && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/55 p-4">
          <div className="w-full max-w-md rounded-3xl bg-white p-6 text-zinc-900 shadow-2xl">
            <div className="flex items-start justify-between gap-4">
              <div>
                <h2 className="text-xl font-bold text-[#241B3A]">Edit profil</h2>
                <p className="mt-1 text-sm text-zinc-500">
                  Perbarui nama yang tampil di Legal-Verse.
                </p>
              </div>
              <button
                type="button"
                onClick={() => setIsEditing(false)}
                aria-label="Tutup"
                className="rounded-full p-2 text-zinc-500 hover:bg-zinc-100"
              >
                <X className="h-5 w-5" />
              </button>
            </div>
            <form onSubmit={(event) => void handleSave(event)} className="mt-6 space-y-4">
              <label className="block">
                <span className="mb-1.5 block text-sm font-semibold">Nama</span>
                <input
                  value={name}
                  onChange={(event) => setName(event.target.value)}
                  maxLength={80}
                  autoFocus
                  className="w-full rounded-xl border border-zinc-200 px-4 py-3 outline-none transition focus:border-purple-500 focus:ring-2 focus:ring-purple-100"
                  placeholder="Nama lengkap"
                />
              </label>
              <label className="block">
                <span className="mb-1.5 block text-sm font-semibold">Email</span>
                <input
                  value={user?.email ?? ""}
                  readOnly
                  className="w-full cursor-not-allowed rounded-xl border border-zinc-200 bg-zinc-100 px-4 py-3 text-zinc-500"
                />
              </label>
              {error && <p className="text-sm text-red-600">{error}</p>}
              <button
                type="submit"
                disabled={isSaving}
                className="flex w-full items-center justify-center gap-2 rounded-xl bg-purple-700 px-4 py-3 font-semibold text-white transition hover:bg-purple-800 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {isSaving && <LoaderCircle className="h-4 w-4 animate-spin" />}
                {isSaving ? "Menyimpan..." : "Simpan perubahan"}
              </button>
            </form>
          </div>
        </div>
      )}
    </>
  );
}
