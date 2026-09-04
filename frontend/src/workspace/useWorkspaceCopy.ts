import { useLocale } from "../providers/LocaleProvider";
import { workspaceCopy } from "./copy";
import type { WorkspaceCopyKey } from "./copy";

export function useWorkspaceCopy() {
  const { locale } = useLocale();
  return (key: WorkspaceCopyKey) => workspaceCopy[locale][key];
}
