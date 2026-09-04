import { FormEvent, useState } from "react";
import { Link, Navigate, useLocation, useNavigate } from "react-router-dom";
import { ApiError } from "../api";
import { BrandMark } from "../components/Brand";
import { Icon } from "../components/Icon";
import { PublicHeader } from "../components/PublicHeader";
import { CopyKey } from "../copy";
import { useAuth } from "../providers/AuthProvider";
import { useLocale } from "../providers/LocaleProvider";

type Mode = "login" | "register";
type Errors = Partial<Record<"identity" | "username" | "email" | "password" | "server", string>>;

function safeNext(search: string) {
  const candidate = new URLSearchParams(search).get("next") || "/workspace/new";
  return candidate.startsWith("/") && !candidate.startsWith("//") ? candidate : "/workspace/new";
}

function localizedServerError(error: unknown, mode: Mode): CopyKey {
  if (error instanceof ApiError) {
    if (mode === "login" && error.status === 401) return "invalidCredentials";
    if (mode === "register" && error.status === 409) return "duplicateIdentity";
  }
  return "requestFailed";
}

function localizedValidationErrors(error: unknown, t: (key: CopyKey) => string): Errors | null {
  if (!(error instanceof ApiError) || error.status !== 422 || error.fields.length === 0) return null;
  const errors: Errors = {};
  for (const field of error.fields) {
    if (field === "username") errors.username = t("usernameLong");
    if (field === "email") errors.email = t("emailLong");
    if (field === "password") errors.password = t("passwordLong");
  }
  return Object.keys(errors).length ? errors : null;
}

export function AuthPage({ mode }: { mode: Mode }) {
  const { checking, user, login, register } = useAuth();
  const { t } = useLocale();
  const location = useLocation();
  const navigate = useNavigate();
  const [errors, setErrors] = useState<Errors>({});
  const [pending, setPending] = useState(false);
  const next = safeNext(location.search);

  if (!checking && user) return <Navigate to={next} replace/>;

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const identity = String(data.get("identity") || "").trim();
    const username = String(data.get("username") || "").trim();
    const email = String(data.get("email") || "").trim();
    const password = String(data.get("password") || "");
    const nextErrors: Errors = {};
    if (mode === "login" && !identity) nextErrors.identity = t("identityRequired");
    if (mode === "register" && !username) nextErrors.username = t("usernameRequired");
    else if (mode === "register" && username.length < 3) nextErrors.username = t("usernameShort");
    else if (mode === "register" && username.length > 50) nextErrors.username = t("usernameLong");
    if (mode === "register" && !email) nextErrors.email = t("emailRequired");
    else if (mode === "register" && email.length > 255) nextErrors.email = t("emailLong");
    else if (mode === "register" && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) nextErrors.email = t("emailInvalid");
    if (!password) nextErrors.password = t("passwordRequired");
    else if (password.length < 8) nextErrors.password = t("passwordShort");
    else if (password.length > 128) nextErrors.password = t("passwordLong");
    if (Object.keys(nextErrors).length) { setErrors(nextErrors); return; }
    setErrors({}); setPending(true);
    try {
      if (mode === "login") await login(identity, password);
      else await register({ username, email, password });
      navigate(next, { replace: true });
    } catch (error) {
      setErrors(mode === "register" ? localizedValidationErrors(error, t) || { server: t(localizedServerError(error, mode)) } : { server: t(localizedServerError(error, mode)) });
      setPending(false);
    }
  }

  const loginMode = mode === "login";
  return (
    <div className="auth-site">
      <PublicHeader/>
      <main className="auth-main section-shell">
        <section className="auth-story">
          <span className="eyebrow"><i/>{t("heroEyebrow")}</span>
          <h2>{t("queueTitle")}</h2><p>{t("queueBody")}</p>
          <div className="auth-flow" aria-hidden="true"><span><Icon name="layers"/></span><i/><span><Icon name="clock"/></span><i/><span><Icon name="chart"/></span></div>
        </section>
        <section className="auth-card">
          <BrandMark size={46}/>
          <h1>{t(loginMode ? "authLoginTitle" : "authRegisterTitle")}</h1>
          <p>{t(loginMode ? "authLoginBody" : "authRegisterBody")}</p>
          <form onSubmit={submit} noValidate>
            {loginMode ? <Field label={t("identity")} name="identity" autoComplete="username" placeholder={t("identityPlaceholder")} error={errors.identity}/> : <>
              <Field label={t("username")} name="username" autoComplete="username" placeholder={t("usernamePlaceholder")} error={errors.username} required maxLength={50}/>
              <Field label={t("email")} name="email" type="email" autoComplete="email" placeholder={t("emailPlaceholder")} error={errors.email} required maxLength={255}/>
            </>}
            <Field label={t("password")} name="password" type="password" autoComplete={loginMode ? "current-password" : "new-password"} placeholder={t("passwordPlaceholder")} error={errors.password} required maxLength={128}/>
            {errors.server && <div className="form-alert" role="alert">{errors.server}</div>}
            <button className="button button-primary auth-submit" disabled={pending}>{t(pending ? (loginMode ? "submittingLogin" : "submittingRegister") : (loginMode ? "submitLogin" : "submitRegister"))}<Icon name="arrow"/></button>
          </form>
          <div className="auth-switch"><span>{t(loginMode ? "noAccount" : "hasAccount")}</span><Link to={loginMode ? `/register?next=${encodeURIComponent(next)}` : `/login?next=${encodeURIComponent(next)}`}>{t(loginMode ? "goRegister" : "goLogin")}</Link></div>
        </section>
      </main>
    </div>
  );
}

function Field({ label, name, type = "text", autoComplete, placeholder, error, required, maxLength }: { label: string; name: string; type?: string; autoComplete: string; placeholder: string; error?: string; required?: boolean; maxLength?: number }) {
  const errorId = `${name}-error`;
  return <div className={`form-field ${error ? "has-error" : ""}`}><label htmlFor={name}>{label}</label><input id={name} name={name} type={type} autoComplete={autoComplete} placeholder={placeholder} required={required} maxLength={maxLength} aria-invalid={Boolean(error)} aria-describedby={error ? errorId : undefined}/>{error && <small id={errorId}>{error}</small>}</div>;
}
