import { AdminDialog } from "./AdminDialog";
export function AdminMetadataDrawer({ title, fields, onClose }: { title: string; fields: [string, string | number][]; onClose: () => void }) {
  return <AdminDialog title={title} drawer onClose={onClose}><dl className="admin-metadata">{fields.map(([label, value], index) => <div key={`${label}-${index}`}><dt>{label}</dt><dd>{String(value)}</dd></div>)}</dl></AdminDialog>;
}
