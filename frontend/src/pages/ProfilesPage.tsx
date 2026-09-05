import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { Icon } from "../components/Icon";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { ProfileEditor } from "../components/ProfileEditor";
import { WorkspaceSelect } from "../components/WorkspaceSelect";
import { WorkspaceState } from "../components/WorkspaceState";
import { useLocale } from "../providers/LocaleProvider";
import { analystApi } from "../analyst/api";
import { useAnalystCopy } from "../analyst/copy";
import { useWorkspaceCopy } from "../workspace/useWorkspaceCopy";
import type { TrainingProfile } from "../analyst/types";
import "../styles/profiles.css";

const PAGE_SIZE = 20;
export function ProfilesPage() {
  const t = useAnalystCopy(); const wt = useWorkspaceCopy(); const { locale } = useLocale();
  const [profiles, setProfiles] = useState<TrainingProfile[]>([]);
  const [loading, setLoading] = useState(true); const [error, setError] = useState(false); const [revision, setRevision] = useState(0);
  const [editing, setEditing] = useState<TrainingProfile | "new" | null>(null);
  const [deleting, setDeleting] = useState<TrainingProfile | null>(null); const [busy, setBusy] = useState(false);
  const [mutationError, setMutationError] = useState(false);
  const [search, setSearch] = useState(""); const [kind, setKind] = useState(""); const [page, setPage] = useState(1);
  const mounted = useRef(true); const removing = useRef(false); const createButton = useRef<HTMLButtonElement>(null);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  useEffect(() => {
    const controller = new AbortController(); setLoading(true); setError(false);
    analystApi.profiles(controller.signal).then(value => { if (!controller.signal.aborted) setProfiles(value); })
      .catch(() => { if (!controller.signal.aborted) setError(true); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [revision]);
  const filtered = profiles.filter(profile => profile.name.toLocaleLowerCase().includes(search.trim().toLocaleLowerCase()) && (!kind || profile.kind === kind));
  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const currentPage = Math.min(page, totalPages);
  const visible = filtered.slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE);
  const clearFilters = () => { setSearch(""); setKind(""); setPage(1); };
  const remove = async () => {
    if (!deleting || removing.current) return;
    removing.current = true; setBusy(true); setMutationError(false);
    try {
      await analystApi.deleteProfile(deleting.id);
      if (!mounted.current) return;
      setProfiles(values => values.filter(profile => profile.id !== deleting.id)); setDeleting(null);
      createButton.current?.focus();
    } catch { if (mounted.current) setMutationError(true); }
    finally { removing.current = false; if (mounted.current) setBusy(false); }
  };
  return <div className="workspace-page task-list-page profiles-page">
    <header className="workspace-page-header"><h1>{t("profiles")}</h1>
      <div className="task-filters profile-filters">
        <label className="search-field"><span className="sr-only">{locale === "zh" ? "搜索档案" : "Search profiles"}</span><Icon name="search"/><input type="search" value={search} placeholder={locale === "zh" ? "搜索档案" : "Search profiles"} onChange={event => { setSearch(event.target.value); setPage(1); }}/></label>
        <WorkspaceSelect aria-label={t("kind")} value={kind} onChange={event => { setKind(event.target.value); setPage(1); }}><option value="">{locale === "zh" ? "全部类型" : "All types"}</option><option value="player">{t("playerKind")}</option><option value="team">{t("teamKind")}</option></WorkspaceSelect>
        <button ref={createButton} disabled={loading || error} className="button button-primary button-icon" type="button" aria-label={t("newProfile")} title={t("newProfile")} onClick={() => setEditing("new")}><Icon name="plus"/></button>
      </div>
    </header>
    {loading ? <div className="loading-block" role="status" aria-label={t("loading")}/> : error ? <WorkspaceState title={t("profileError")} onRetry={() => setRevision(value => value + 1)}/>
      : profiles.length === 0 ? <WorkspaceState icon="team" title={locale === "zh" ? "还没有训练档案" : "No training profiles yet"} body={t("noProfiles")} action={<button className="button button-primary" type="button" onClick={() => setEditing("new")}><Icon name="plus"/>{t("newProfile")}</button>}/>
      : !filtered.length ? <WorkspaceState icon="search" title={locale === "zh" ? "没有符合条件的档案" : "No matching profiles"} body={locale === "zh" ? "试试其他名称或档案类型。" : "Try another name or profile type."} action={<button className="button button-outline" type="button" onClick={clearFilters}>{locale === "zh" ? "清除筛选" : "Clear filters"}</button>}/>
      : <div className="task-table-wrap" role="region" aria-label={t("profiles")} tabIndex={0}><table className="task-table profiles-table"><thead><tr><th>{t("name")}</th><th>{t("kind")}</th><th>{t("goals")}</th><th>{locale === "zh" ? "更新时间" : "Updated"}</th><th>{wt("actions")}</th></tr></thead><tbody>{visible.map(profile => <tr key={profile.id}>
        <td><Link className="task-title-link" to={`/workspace/profiles/${encodeURIComponent(profile.id)}`}><span className="task-file-icon"><Icon name={profile.kind === "player" ? "user" : "team"} size={18}/></span><span><b>{profile.name}</b></span></Link></td>
        <td>{t(profile.kind === "player" ? "playerKind" : "teamKind")}</td><td><span className="profile-goals" title={profile.goals}>{profile.goals || "—"}</span></td>
        <td><time dateTime={profile.updated_at}>{new Date(profile.updated_at).toLocaleDateString(locale === "zh" ? "zh-CN" : "en")}</time></td>
        <td><div className="table-actions"><Link className="table-action" to={`/workspace/profiles/${encodeURIComponent(profile.id)}`} aria-label={`${wt("open")} · ${profile.name}`} title={`${wt("open")} · ${profile.name}`}><Icon name="arrow"/></Link><button className="table-action" type="button" aria-label={`${t("editProfile")} · ${profile.name}`} title={`${t("editProfile")} · ${profile.name}`} onClick={() => setEditing(profile)}><Icon name="pencil"/></button><button className="table-action action-delete" type="button" aria-label={`${t("deleteProfile")} · ${profile.name}`} title={`${t("deleteProfile")} · ${profile.name}`} onClick={() => { setMutationError(false); setDeleting(profile); }}><Icon name="trash"/></button></div></td>
      </tr>)}</tbody></table></div>}
    {!loading && !error && profiles.length > 0 && <footer className="pagination"><span>{locale === "zh" ? "共" : "Total profiles"} {filtered.length}</span><div><button type="button" aria-label={wt("previous")} title={wt("previous")} disabled={currentPage <= 1} onClick={() => setPage(currentPage - 1)}><Icon name="chevronLeft" size={18}/></button><span className="pagination-current" aria-current="page">{currentPage} / {totalPages}</span><button type="button" aria-label={wt("next")} title={wt("next")} disabled={currentPage >= totalPages} onClick={() => setPage(currentPage + 1)}><Icon name="chevronRight" size={18}/></button></div><span>{PAGE_SIZE} / {wt("perPage")}</span></footer>}
    {editing && <ProfileEditor profile={editing === "new" ? null : editing} onClose={() => setEditing(null)} onSaved={profile => {
      setProfiles(values => values.some(value => value.id === profile.id) ? values.map(value => value.id === profile.id ? profile : value) : [profile, ...values]);
      if (editing === "new") clearFilters();
      setEditing(null);
      createButton.current?.focus();
    }}/>}
    {deleting && <ConfirmDialog title={t("deleteProfile")} message={mutationError ? t("saveError") : `${deleting.name} · ${t("deleteBody")}`} confirmLabel={t("deleteProfile")} danger busy={busy} onConfirm={() => void remove()} onClose={() => { setDeleting(null); setMutationError(false); }}/>}
  </div>;
}
