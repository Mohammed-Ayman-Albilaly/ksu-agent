import { SiteFooter } from "@/components/SiteFooter";
import { SiteHeader } from "@/components/SiteHeader";
import { Features } from "@/components/home/Features";
import { Hero } from "@/components/home/Hero";
import { HowItWorks } from "@/components/home/HowItWorks";
import { SourceNote } from "@/components/home/SourceNote";

export default function Home() {
  return (
    <div className="flex min-h-screen flex-col bg-white">
      <SiteHeader />
      <main id="main" className="flex-1">
        <Hero />
        <Features />
        <HowItWorks />
        <SourceNote />
      </main>
      <SiteFooter />
    </div>
  );
}
