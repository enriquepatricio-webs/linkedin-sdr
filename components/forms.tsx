"use client";

import { useActionState, type ReactNode } from "react";
import { useFormStatus } from "react-dom";
import { runJob as runJobAction, type ActionState } from "@/app/actions";

export function Submit({ children, className, pendingText = "…", name, value }: { children: ReactNode; className: string; pendingText?: string; name?: string; value?: string }) {
  const { pending } = useFormStatus();
  return (
    <button type="submit" className={className} disabled={pending} name={name} value={value}>
      {pending ? pendingText : children}
    </button>
  );
}

export function Feedback({ state }: { state: ActionState }) {
  if (!state) return null;
  return (
    <p className={`mt-2 break-words text-sm ${state.ok ? "text-emerald-700" : "text-rose-700"}`} role="status">
      {state.message}
    </p>
  );
}

// Formulario que muestra el resultado de una server action (state, formData) => ActionState.
export function ActionForm({
  action,
  children,
  className,
}: {
  action: (state: ActionState, fd: FormData) => Promise<ActionState>;
  children: ReactNode;
  className?: string;
}) {
  const [state, formAction] = useActionState(action, null);
  return (
    <form action={formAction} className={className}>
      {children}
      <Feedback state={state} />
    </form>
  );
}

export function JobButton({ job, label, campaignId, className }: { job: string; label: string; campaignId?: string; className: string }) {
  return (
    <ActionForm action={runJobAction}>
      <input type="hidden" name="job" value={job} />
      {campaignId && <input type="hidden" name="campaign_id" value={campaignId} />}
      <Submit className={className} pendingText="Ejecutando…">
        {label}
      </Submit>
    </ActionForm>
  );
}
