"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";

export default function SplashPage() {
  const router = useRouter();
  const [opacity, setOpacity] = useState(1);
  const doneRef = useRef(false);
  const fallbackRef = useRef<ReturnType<typeof setTimeout>>(undefined);

  const handleEnd = () => {
    if (doneRef.current) return;
    doneRef.current = true;
    if (fallbackRef.current) clearTimeout(fallbackRef.current);
    setOpacity(0);
    setTimeout(() => router.push("/login"), 500);
  };

  useEffect(() => {
    // Hard fallback: 8s max
    fallbackRef.current = setTimeout(handleEnd, 8000);
    return () => {
      if (fallbackRef.current) clearTimeout(fallbackRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div
      className="relative flex h-screen w-screen items-center justify-center overflow-hidden"
      style={{
        background: "#000",
        opacity,
        transition: "opacity 0.5s ease",
      }}
    >
      {/* Video */}
      <video
        className="absolute inset-0 h-full w-full object-cover"
        src="/teaser.mp4"
        autoPlay
        muted
        playsInline
        onEnded={handleEnd}
        onError={handleEnd}
      />

      {/* Bottom fade overlay */}
      <div
        className="absolute inset-0 pointer-events-none"
        style={{
          background: "linear-gradient(to bottom, transparent 55%, rgba(0,0,0,0.8) 100%)",
        }}
      />

      {/* Skip button */}
      <button
        onClick={handleEnd}
        className="absolute bottom-8 right-8 text-sm font-medium tracking-widest transition-colors duration-200"
        style={{ color: "rgba(255,255,255,0.35)", zIndex: 10 }}
        onMouseEnter={(e) => { (e.currentTarget as HTMLButtonElement).style.color = "rgba(255,255,255,0.85)"; }}
        onMouseLeave={(e) => { (e.currentTarget as HTMLButtonElement).style.color = "rgba(255,255,255,0.35)"; }}
      >
        Passer ›
      </button>
    </div>
  );
}
