import Link from "next/link";

/** The Ictus wordmark from ictus-logo.png. */
export function SpinningLogo() {
  return (
    <Link href="/" className="brand-mark">
      <img src="/ictus-logo.png" alt="ictus" className="brand-logo" />
    </Link>
  );
}
