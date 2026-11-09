import { SiteFooter } from "@/components/SiteFooter";
import { SiteHeader } from "@/components/SiteHeader";

export default function AuthLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <div className="flex min-h-screen flex-col bg-surface">
      <SiteHeader />
      <main
        id="main"
        className="flex flex-1 items-center justify-center px-5 py-12 sm:px-8"
      >
        <div className="w-full max-w-[440px]">{children}</div>
      </main>
      <SiteFooter />
    </div>
  );
}
