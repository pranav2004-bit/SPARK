"use client";

import { useState } from "react";
import Link from "next/link";
import { Menu, X } from "lucide-react";

export function LandingMobileMenu() {
  const [isOpen, setIsOpen] = useState(false);

  return (
    <div className="md:hidden flex items-center">
      {/* Toggle Button */}
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="flex items-center justify-center p-1.5 ml-0.5 text-[var(--color-text-muted)] hover:text-[var(--color-text)] rounded-md transition-colors border border-transparent bg-transparent"
        aria-label="Toggle menu"
        style={{ WebkitTapHighlightColor: 'transparent' }}
      >
        {isOpen ? <X size={24} strokeWidth={2.2} /> : <Menu size={24} strokeWidth={2.2} />}
      </button>

      {/* Dropdown Panel */}
      {isOpen && (
        <div 
          className="absolute left-0 right-0 bg-white border-t border-b border-[var(--color-border)] z-[60] flex flex-col"
          style={{ top: "100%" }} // Anchors exactly below the navbar
        >
          <div className="px-6 py-3 flex flex-col gap-1 text-left w-full items-start">
            <a 
              href="#features" 
              onClick={() => setIsOpen(false)} 
              className="block py-2.5 w-full text-[15px] text-[var(--color-text-muted)] hover:text-[var(--color-text)] transition-colors font-medium relative"
            >
              Modules
            </a>
            <a 
              href="#how-it-works" 
              onClick={() => setIsOpen(false)} 
              className="block py-2.5 w-full text-[15px] text-[var(--color-text-muted)] hover:text-[var(--color-text)] transition-colors font-medium"
            >
              Process
            </a>
            <Link 
              href="/about" 
              onClick={() => setIsOpen(false)} 
              className="block py-2.5 w-full text-[15px] text-[var(--color-text-muted)] hover:text-[var(--color-text)] transition-colors font-medium"
            >
              About
            </Link>
          </div>
          
          {/* Divider */}
          <div className="w-[calc(100%-3rem)] mx-auto h-px bg-[var(--color-border)] opacity-60" />
          
          {/* Sign In (Centered as per screenshot) */}
          <div className="px-6 py-4">
            <Link 
              href="/students/login" 
              className="block text-[15px] text-[var(--color-text)] font-bold text-center w-full transition-colors hover:text-[var(--color-primary)]"
            >
              Sign In
            </Link>
          </div>
        </div>
      )}
    </div>
  );
}
