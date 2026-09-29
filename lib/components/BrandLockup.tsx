import Image from "next/image";

type BrandLockupProps = {
  className?: string;
  preload?: boolean;
  theme?: "dark" | "light";
  variant?: "hero" | "login" | "sidebar";
};

const variantStyles = {
  hero: {
    divider: "h-10",
    kyri: "h-14",
    legalVerse: "h-12",
    wrapper: "gap-3",
  },
  login: {
    divider: "h-7",
    kyri: "h-10",
    legalVerse: "h-9",
    wrapper: "gap-2.5",
  },
  sidebar: {
    divider: "h-7",
    kyri: "h-9",
    legalVerse: "h-9",
    wrapper: "gap-2",
  },
} as const;

export function BrandLockup({
  className = "",
  preload = false,
  theme = "light",
  variant = "sidebar",
}: BrandLockupProps) {
  const styles = variantStyles[variant];
  const darkSurface = theme === "dark";

  return (
    <div
      className={`flex shrink-0 items-center ${styles.wrapper} ${className}`}
      aria-label="Legal-Verse dan Komisi Yudisial Republik Indonesia"
    >
      <Image
        src={darkSurface ? "/logo.png" : "/logo_dark.png"}
        alt="Legal-Verse"
        width={480}
        height={320}
        preload={preload}
        className={`${styles.legalVerse} w-auto object-contain`}
      />
      <span
        aria-hidden="true"
        className={`${styles.divider} w-px ${darkSurface ? "bg-white/20" : "bg-zinc-200"}`}
      />
      <Image
        src="/logo-kyri.png"
        alt="Komisi Yudisial Republik Indonesia"
        width={408}
        height={385}
        preload={preload}
        className={`${styles.kyri} w-auto object-contain ${
          darkSurface
            ? "drop-shadow-[0_0_2px_rgba(255,255,255,0.8)]"
            : ""
        }`}
      />
    </div>
  );
}
