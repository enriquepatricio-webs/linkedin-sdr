"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const LINKS = [
  { href: "/", label: "Resumen" },
  { href: "/aprobaciones", label: "Aprobaciones", badge: true },
  { href: "/leads", label: "Leads" },
  { href: "/campanas", label: "Campañas" },
  { href: "/actividad", label: "Actividad" },
  { href: "/ajustes", label: "Ajustes" },
];

export function Nav({ pending }: { pending: number }) {
  const path = usePathname();
  return (
    <nav className="flex gap-1 overflow-x-auto md:flex-col">
      {LINKS.map((l) => {
        const active = l.href === "/" ? path === "/" : path.startsWith(l.href);
        return (
          <Link
            key={l.href}
            href={l.href}
            className={`flex items-center justify-between gap-2 whitespace-nowrap rounded-lg px-3 py-2 text-sm font-medium ${
              active ? "bg-slate-900 text-white" : "text-slate-600 hover:bg-slate-200/60 hover:text-slate-900"
            }`}
          >
            {l.label}
            {l.badge && pending > 0 && (
              <span className={`rounded-full px-1.5 text-xs ${active ? "bg-white text-slate-900" : "bg-amber-500 text-white"}`}>{pending}</span>
            )}
          </Link>
        );
      })}
    </nav>
  );
}
