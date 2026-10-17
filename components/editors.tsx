"use client";

import { useActionState } from "react";
import { approveInvite, approveMessage, inviteNow, rejectInvite, rejectMessage, sendMessageNow } from "@/app/actions";
import { Feedback, Submit } from "./forms";
import { btnDanger, btnPrimary, btnSuccess, input } from "./ui";

// Todos los botones usan el texto tal y como está en la caja.

export function InviteEditor({ id, note }: { id: string; note: string }) {
  const [state, inviteAction] = useActionState(inviteNow, null);
  return (
    <form action={approveInvite} className="mt-3 space-y-2">
      <input type="hidden" name="id" value={id} />
      <textarea name="connection_note" defaultValue={note} maxLength={200} rows={2} className={input} placeholder="Sin nota" />
      <div className="flex flex-wrap gap-2">
        <Submit className={btnSuccess}>Aprobar</Submit>
        <button formAction={inviteAction} className={btnPrimary}>
          Invitar ya
        </button>
        <button formAction={rejectInvite} className={btnDanger}>
          Descartar
        </button>
      </div>
      <Feedback state={state} />
    </form>
  );
}

export function DraftEditor({ id, body, approveLabel = "Aprobar" }: { id: string; body: string; approveLabel?: string }) {
  const [state, sendAction] = useActionState(sendMessageNow, null);
  return (
    <form action={approveMessage} className="space-y-2">
      <input type="hidden" name="id" value={id} />
      <textarea name="body" defaultValue={body} rows={Math.min(8, Math.max(3, Math.ceil(body.length / 80)))} className={input} />
      <div className="flex flex-wrap gap-2">
        <Submit className={btnSuccess}>{approveLabel}</Submit>
        <button formAction={sendAction} className={btnPrimary}>
          Enviar ya
        </button>
        <button formAction={rejectMessage} className={btnDanger}>
          Rechazar
        </button>
      </div>
      <Feedback state={state} />
    </form>
  );
}
