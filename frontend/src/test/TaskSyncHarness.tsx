// Isolated development fixture for scripts/check-task-sync-layout.mjs; never imported by the app.
import { createRoot } from "react-dom/client";
import { useState } from "react";
import { LocaleProvider } from "../providers/LocaleProvider";
import { VideoSyncDialog } from "../components/VideoSyncDialog";
import "../styles.css";
import "../styles/workspace.css";

function Harness() {
  const [open, setOpen] = useState(false);
  return <LocaleProvider><button onClick={() => setOpen(true)}>Open fixture</button>{open && <VideoSyncDialog taskId="synthetic-sync" onClose={() => setOpen(false)} onConfirmed={() => setOpen(false)}/>}</LocaleProvider>;
}
createRoot(document.getElementById("root")!).render(<Harness/>);
