import { useRef, useState } from "react";
import { NavLink, Outlet } from "react-router-dom";
import { PublicHeader } from "./PublicHeader";
import { Icon } from "./Icon";
import { useLocale } from "../providers/LocaleProvider";
import { apiCopy } from "../apiCenter/copy";
import { useMediaQuery } from "../apiCenter/useMediaQuery";

export function ApiShell() {
  const { locale } = useLocale();
  const c = apiCopy[locale];
  const mobile = useMediaQuery("(max-width: 767px)");
  const [mobileOpen, setMobileOpen] = useState(false);
  const [groupOpen, setGroupOpen] = useState(true);
  const menuRef = useRef<HTMLButtonElement>(null);
  const open = mobile ? mobileOpen : groupOpen;
  const setOpen = mobile ? setMobileOpen : setGroupOpen;
  const closeMenu = () => {
    if (!mobile) return;
    setMobileOpen(false);
    menuRef.current?.focus();
  };

  return <div className="public-site api-site">
    <PublicHeader/>
    <div className="api-layout">
      <aside className="api-sidebar" aria-label={c.nav} onKeyDown={event => {
        if (event.key === "Escape" && open) {
          event.preventDefault();
          setOpen(false);
          menuRef.current?.focus();
        }
      }}>
        <button ref={menuRef} className="api-product-toggle" type="button" aria-label={mobile ? (open ? c.close : c.menu) : "DaShanBing API"} aria-expanded={open} aria-controls="api-navigation" onClick={() => setOpen(!open)}>
          <Icon name="code" size={18}/><span>DaShanBing API</span><span className="api-chevron" aria-hidden="true"/>
        </button>
        <nav id="api-navigation" aria-label={c.nav} hidden={!open}>
          <NavLink to="/api/docs" onClick={closeMenu}>{c.docs}</NavLink>
          <NavLink to="/api/keys" onClick={closeMenu}>{c.keys}</NavLink>
        </nav>
      </aside>
      <Outlet/>
    </div>
  </div>;
}
