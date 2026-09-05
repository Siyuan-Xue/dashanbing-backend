import type { SelectHTMLAttributes } from "react";
import { Icon } from "./Icon";

export function WorkspaceSelect(props: SelectHTMLAttributes<HTMLSelectElement>) {
  return <span className="workspace-select"><select {...props}/><Icon name="chevronDown" size={16}/></span>;
}
