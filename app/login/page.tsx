import { login } from "@/app/actions";
import { ActionForm, Submit } from "@/components/forms";
import { btnPrimary, input } from "@/components/ui";

export default function LoginPage() {
  return (
    <div className="flex min-h-screen items-center justify-center p-4">
      <div className="w-full max-w-sm rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
        <h1 className="text-lg font-semibold">LinkedIn SDR</h1>
        <p className="mb-4 text-sm text-slate-500">The Coto Company</p>
        <ActionForm action={login} className="space-y-3">
          <input name="password" type="password" placeholder="Contraseña" className={input} autoFocus required />
          <Submit className={`${btnPrimary} w-full`}>Entrar</Submit>
        </ActionForm>
      </div>
    </div>
  );
}
