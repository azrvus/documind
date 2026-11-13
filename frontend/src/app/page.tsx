"use client";

import { type FormEvent, type ReactNode, useCallback, useEffect, useRef, useState } from "react";
import { Activity, ArrowUp, BookOpen, FileText, Files, FolderOpen, HelpCircle, LoaderCircle, Menu, Moon, Plus, Search, Send, Settings2, ShieldCheck, Sparkles, Sun, Trash2, UploadCloud, X } from "lucide-react";
import { api, type Citation, type Collection, type DocumentDetail, type DocumentItem, type Health, type SearchResult } from "@/lib/api";

type Message = { query: string; result?: SearchResult; error?: string };
type View = string;
type Panel = { type: "help" } | { type: "settings" } | { type: "create" } | { type: "rename"; collection: Collection } | { type: "document"; id: string; passage?: string } | { type: "delete-document"; document: DocumentItem } | { type: "delete-collection"; collection: Collection };

function errorText(error: unknown) { return error instanceof Error ? error.message : "Something went wrong. Try again."; }
function timeLabel(iso: string) { return new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric", year: "numeric" }).format(new Date(iso)); }
function sizeLabel(bytes: number | null) {
  if (bytes === null) return null;
  return bytes < 1024 ? `${bytes} B` : bytes < 1048576 ? `${(bytes / 1024).toFixed(1)} KB` : `${(bytes / 1048576).toFixed(1)} MB`;
}
function FileGlyph({ type }: { type: string }) {
  return <div className={`file-glyph ${type}`} aria-hidden="true"><FileText size={19} strokeWidth={1.7} /><small>{type.toUpperCase()}</small></div>;
}
function Modal({ title, children, close, className = "" }: { title: string; children: ReactNode; close: () => void; className?: string }) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const dialog = ref.current;
    dialog?.showModal();
    return () => dialog?.close();
  }, []);
  return <dialog ref={ref} className={`modal ${className}`} aria-labelledby="modal-title" onCancel={event => { event.preventDefault(); close(); }}>
    <header className="modal-header"><h2 id="modal-title">{title}</h2><button className="icon-btn" type="button" aria-label="Close dialog" onClick={close}><X size={19} /></button></header>
    {children}
  </dialog>;
}

export default function Home() {
  const [documents, setDocuments] = useState<DocumentItem[]>([]);
  const [collections, setCollections] = useState<Collection[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [messages, setMessages] = useState<Message[]>([]);
  const [question, setQuestion] = useState("");
  const [filenameFilter, setFilenameFilter] = useState("");
  const [health, setHealth] = useState<Health | null>(null);
  const [checking, setChecking] = useState(true);
  const [loaded, setLoaded] = useState(false);
  const [busy, setBusy] = useState(false);
  const [uploading, setUploading] = useState("");
  const uploadLock = useRef(false);
  const [dragging, setDragging] = useState(false);
  const [error, setError] = useState("");
  const [uploadNote, setUploadNote] = useState("");
  const [dark, setDark] = useState(false);
  const [name, setName] = useState("Aziz");
  const [mobileNav, setMobileNav] = useState(false);
  const [view, setView] = useState<View>("workspace");
  const [panel, setPanel] = useState<Panel | null>(null);
  const [draft, setDraft] = useState("");
  const [detail, setDetail] = useState<DocumentDetail | null>(null);
  const [panelError, setPanelError] = useState("");
  const [saving, setSaving] = useState(false);
  const [provider, setProvider] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);
  const questionRef = useRef<HTMLTextAreaElement>(null);
  const resultsRef = useRef<HTMLDivElement>(null);
  const navToggle = useRef<HTMLButtonElement>(null);
  const navClose = useRef<HTMLButtonElement>(null);
  const activeCollection = collections.find(item => item.id === view);
  const scope = activeCollection ? documents.filter(doc => doc.collection_id === activeCollection.id) : documents;
  const visible = scope.filter(doc => doc.filename.toLocaleLowerCase().includes(filenameFilter.trim().toLocaleLowerCase()));
  const selectedInScope = selected.filter(id => scope.some(doc => doc.id === id));
  const preview = view === "workspace" && !filenameFilter.trim();
  const displayed = preview ? visible.slice(0, 4) : visible;
  const initial = Array.from(name)[0]?.toLocaleUpperCase() || "A";
  const location = activeCollection?.name ?? (view === "documents" ? "All documents" : "Overview");
  const providerStatus = health ? ({ not_configured: "Not configured", unverified: "Unverified", ready: "Ready", error: "Error" }[health.provider_status]) : "Unavailable";
  const useProvider = Boolean(provider && health?.ai_configured);

  const checkHealth = useCallback(async () => {
    try { setHealth(await api<Health>("/api/health", { signal: AbortSignal.timeout(5000) })); }
    catch { setHealth(null); }
    finally { setChecking(false); }
  }, []);
  const refresh = useCallback(async () => {
    const [docs, groups] = await Promise.all([
      api<{ documents: DocumentItem[] }>("/api/documents", { signal: AbortSignal.timeout(10000) }),
      api<{ collections: Collection[] }>("/api/collections", { signal: AbortSignal.timeout(10000) }),
    ]);
    setDocuments(docs.documents);
    setCollections(groups.collections);
    setLoaded(true);
    setSelected(ids => ids.filter(id => docs.documents.some(doc => doc.id === id)));
  }, []);
  const reload = useCallback(() => {
    setError("");
    void checkHealth();
    void refresh().catch(e => setError(errorText(e)));
  }, [checkHealth, refresh]);

  useEffect(() => {
    reload();
    setDark(localStorage.getItem("adi-theme") === "dark");
    setName(localStorage.getItem("adi-display-name")?.trim().slice(0, 40) || "Aziz");
    const interval = window.setInterval(() => void checkHealth(), 30000);
    return () => window.clearInterval(interval);
  }, [checkHealth, reload]);

  useEffect(() => {
    const el = resultsRef.current;
    const latest = el?.querySelector(".search-result:last-of-type");
    if (el && latest) el.scrollTop += latest.getBoundingClientRect().top - el.getBoundingClientRect().top;
  }, [messages]);

  useEffect(() => {
    if (!mobileNav) return;
    navClose.current?.focus();
    const desktop = window.matchMedia("(min-width: 901px)");
    const handleResize = () => { if (desktop.matches) setMobileNav(false); };
    desktop.addEventListener("change", handleResize);
    return () => desktop.removeEventListener("change", handleResize);
  }, [mobileNav]);

  useEffect(() => {
    if (panel?.type !== "document") return;
    let current = true;
    void api<DocumentDetail>(`/api/documents/${panel.id}`)
      .then(value => { if (current) setDetail(value); })
      .catch(e => { if (current) setPanelError(errorText(e)); });
    return () => { current = false; };
  }, [panel]);

  useEffect(() => {
    if (!detail || panel?.type !== "document" || !panel.passage) return;
    const target = document.getElementById(`passage-${panel.passage}`);
    target?.focus({ preventScroll: true });
    target?.scrollIntoView({ block: "nearest" });
  }, [detail, panel]);

  function closeNav() {
    setMobileNav(false);
    requestAnimationFrame(() => navToggle.current?.focus());
  }
  function navigate(next: View) {
    setView(next);
    setFilenameFilter("");
    setSelected([]);
    if (mobileNav) closeNav();
  }
  function openPanel(next: Panel, value = "") {
    setDetail(null);
    setPanelError("");
    setDraft(value);
    setPanel(next);
  }
  function showSource(source: Citation) {
    openPanel({ type: "document", id: source.document_id, passage: source.passage_id });
  }
  function toggleTheme() {
    const next = !dark;
    setDark(next);
    localStorage.setItem("adi-theme", next ? "dark" : "light");
  }
  async function upload(files: FileList | File[]) {
    if (uploadLock.current || !files.length) return;
    uploadLock.current = true;
    setError("");
    setUploadNote("");
    const batch = Array.from(files);
    const failures: string[] = [];
    let done = 0;
    try {
      for (const [index, file] of batch.entries()) {
        if (!/\.(pdf|txt)$/i.test(file.name)) { failures.push(`${file.name}: choose a PDF or TXT file.`); continue; }
        if (file.size > 10 * 1024 * 1024) { failures.push(`${file.name}: files must be 10 MB or smaller.`); continue; }
        setUploading(`Uploading and indexing ${index + 1} of ${batch.length}: ${file.name}`);
        const form = new FormData();
        form.append("file", file);
        try { await api("/api/documents", { method: "POST", body: form }); done++; }
        catch (e) { failures.push(`${file.name}: ${errorText(e)}`); }
      }
      if (done) {
        try { await refresh(); }
        catch (e) { failures.push(errorText(e)); }
        setUploadNote(`${done} ${done === 1 ? "document" : "documents"} indexed and ready in All documents.`);
      }
      setError(failures.join("\n"));
    } finally {
      setUploading("");
      uploadLock.current = false;
      if (fileRef.current) fileRef.current.value = "";
      void checkHealth();
    }
  }
  async function ask(event: FormEvent) {
    event.preventDefault();
    const clean = question.trim();
    if (!clean || busy || !scope.length) return;
    setQuestion("");
    setBusy(true);
    setMessages(prev => [...prev, { query: clean }]);
    let update: Message;
    try {
      const result = await api<SearchResult>("/api/chat", { method: "POST", body: JSON.stringify({
        question: clean, document_ids: selectedInScope, collection_id: activeCollection?.id ?? null, use_provider: useProvider,
      }) });
      update = { query: clean, result };
    } catch (e) { update = { query: clean, error: errorText(e) }; }
    setMessages(prev => [...prev.slice(0, -1), update]);
    setBusy(false);
    if (useProvider) void checkHealth();
  }

  async function submitPanel(event: FormEvent) {
    event.preventDefault();
    if (!panel || saving) return;
    const clean = draft.trim();
    if (panel.type === "settings") {
      const next = clean || "Aziz";
      localStorage.setItem("adi-display-name", next);
      setName(next);
      setPanel(null);
      return;
    }
    setPanelError("");
    setSaving(true);
    try {
      if (panel.type === "create" || panel.type === "rename") {
        const collection = await api<Collection>(panel.type === "create" ? "/api/collections" : `/api/collections/${panel.collection.id}`, {
          method: panel.type === "create" ? "POST" : "PATCH", body: JSON.stringify({ name: clean }),
        });
        setCollections(items => [...items.filter(item => item.id !== collection.id), collection].sort((a, b) => a.name.localeCompare(b.name)));
        if (panel.type === "create") navigate(collection.id);
      } else if (panel.type === "delete-collection") {
        await api(`/api/collections/${panel.collection.id}`, { method: "DELETE" });
        setCollections(items => items.filter(item => item.id !== panel.collection.id));
        if (view === panel.collection.id) navigate("documents");
      } else if (panel.type === "delete-document") {
        await api(`/api/documents/${panel.document.id}`, { method: "DELETE" });
        setDocuments(items => items.filter(item => item.id !== panel.document.id));
        setSelected(ids => ids.filter(id => id !== panel.document.id));
        setMessages(items => items.filter(item => !item.result?.sources.some(source => source.document_id === panel.document.id)));
      }
      setPanel(null);
      void refresh().catch(e => setError(errorText(e)));
    } catch (e) { setPanelError(errorText(e)); }
    finally { setSaving(false); }
  }

  async function assign(document: DocumentItem, collectionId: string) {
    setSaving(true);
    setPanelError("");
    try {
      const updated = await api<DocumentItem>(`/api/documents/${document.id}`, { method: "PATCH", body: JSON.stringify({ collection_id: collectionId || null }) });
      setDetail(current => current ? { ...current, document: updated } : current);
      setDocuments(items => items.map(item => item.id === updated.id ? updated : item));
      void refresh().catch(e => setError(errorText(e)));
    } catch (e) { setPanelError(errorText(e)); }
    finally { setSaving(false); }
  }

  const openFiles = () => fileRef.current?.click();
  const help = () => openPanel({ type: "help" });
  const settings = () => openPanel({ type: "settings" }, name);
  const closePanel = () => { if (!saving) setPanel(null); };
  const modalTitle = panel?.type === "help" ? "Getting started" : panel?.type === "settings" ? "Local preferences" :
    panel?.type === "create" ? "Create collection" : panel?.type === "rename" ? "Rename collection" :
    panel?.type === "delete-collection" ? "Delete collection" : panel?.type === "delete-document" ? "Delete document" : detail?.document.filename ?? "Document details";
  return <div className={dark ? "shell dark" : "shell"} onKeyDown={event => { if (event.key === "Escape" && mobileNav && !panel) closeNav(); }}>
    {mobileNav && <button className="mobile-scrim" aria-label="Close navigation overlay" onClick={closeNav} />}
    <aside id="workspace-sidebar" className={`sidebar ${mobileNav ? "open" : ""}`}>
      <div className="brand"><div className="brand-mark"><Sparkles size={17} fill="currentColor" /></div><div><strong>documind</strong><span>INTELLIGENCE WORKSPACE</span></div><button ref={navClose} className="icon-btn mobile-close" aria-label="Close navigation" onClick={closeNav}><X size={19} /></button></div>
      <div className="workspace-switch"><div className="workspace-avatar">{initial}</div><div className="workspace-name"><strong>My workspace</strong><span>Single browser workspace</span></div></div>
      <div className="nav-label">WORKSPACE</div>
      <nav className="nav-list" aria-label="Workspace">
        <button className={`nav-item ${view === "workspace" ? "active" : ""}`} aria-current={view === "workspace" ? "page" : undefined} onClick={() => navigate("workspace")}><FolderOpen size={17} /> Overview</button>
        <button className={`nav-item ${view === "documents" ? "active" : ""}`} aria-current={view === "documents" ? "page" : undefined} onClick={() => navigate("documents")}><Files size={17} /> All documents <em>{documents.length}</em></button>
      </nav>
      <div className="nav-label collection-label">COLLECTIONS <button aria-label="Add collection" className="icon-btn" onClick={() => { if (mobileNav) closeNav(); openPanel({ type: "create" }); }}><Plus size={17} /></button></div>
      <nav className="nav-list" aria-label="Collections">
        {collections.map(item => <button className={`nav-item ${view === item.id ? "active" : ""}`} aria-current={view === item.id ? "page" : undefined} key={item.id} onClick={() => navigate(item.id)}><span className="collection-dot" /><span className="collection-name">{item.name}</span><em>{item.document_count}</em></button>)}
        {!collections.length && <span className="empty-collections">No collections yet</span>}
      </nav>
      <div className="sidebar-bottom">
        <button className="nav-item" onClick={() => { if (mobileNav) closeNav(); help(); }}><HelpCircle size={17} /> Getting started</button>
        <div className="privacy-card"><ShieldCheck size={17} /><div><strong>Local storage</strong><p>Browser workspace without a sign-in.</p></div></div>
        <div className="user-row"><div className="user-avatar">{initial}</div><div className="user-name"><strong>{name}</strong><span>Local preference</span></div><button onClick={toggleTheme} className="icon-btn theme-btn" aria-label={dark ? "Use light theme" : "Use dark theme"}>{dark ? <Sun size={17} /> : <Moon size={17} />}</button><button className="icon-btn" aria-label="Settings" onClick={() => { if (mobileNav) closeNav(); settings(); }}><Settings2 size={17} /></button></div>
      </div>
    </aside>
    <main className="main-panel" inert={mobileNav}>
      <header className="topbar"><button ref={navToggle} className="icon-btn mobile-menu" aria-label="Open navigation" aria-expanded={mobileNav} aria-controls="workspace-sidebar" onClick={() => setMobileNav(!mobileNav)}><Menu size={20} /></button>
        <div className="breadcrumbs"><span>Workspace</span><span className="crumb-slash">/</span><strong title={location}>{location}</strong></div>
        <div className="top-actions"><div className="status-pill" role="status"><span className={`status-dot ${health ? "online" : ""}`} /> Backend: {health ? "Connected" : checking ? "Checking…" : "Disconnected"}</div><button className="icon-btn" aria-label="Help" onClick={help}><HelpCircle size={18} /></button><button className="top-avatar" aria-label="Local preferences" onClick={settings}>{initial}</button></div>
      </header>
      <div className="content-area">
        <div className="page-heading"><div><div className="eyebrow"><span className="eyebrow-line" /> YOUR KNOWLEDGE, IN CONTEXT</div><h1>{view === "workspace" ? `Good morning, ${name}.` : location} {view === "workspace" && <span className="wave" aria-hidden="true">✳</span>}</h1><p>{activeCollection ? "Browse this collection and search its documents." : "Bring your documents into focus. Find answers in the source text."}</p></div><button className="button-secondary" onClick={openFiles} disabled={Boolean(uploading)}><Plus size={16} /> Add documents</button></div>
        <input ref={fileRef} type="file" accept=".pdf,.txt,application/pdf,text/plain" multiple hidden onChange={event => { if (event.target.files) void upload(event.target.files); }} />
        {error && <div className="alert-error" role="alert"><span>{error}</span><button className="icon-btn" aria-label="Dismiss error" onClick={() => setError("")}><X size={16} /></button></div>}
        <div className="setup-banner mode-banner"><div className="setup-icon"><Activity size={17} /></div><div><strong>{useProvider ? "OpenAI mode selected" : health ? "Local Mode Active" : "Local Document Search"}</strong><span>{useProvider ? "Questions and retrieved passages may be sent to OpenAI." : "Upload, extract, search, and read source excerpts without a paid API."}</span></div><span className="provider-status">AI provider: {providerStatus}</span>{!health && !checking && <button className="text-button" onClick={reload}>Retry connection</button>}</div>
        <div className="dashboard-grid">
          <div className="left-column">
            <section className="upload-card" aria-label="Upload documents" onDragOver={event => { event.preventDefault(); if (!uploading) setDragging(true); }} onDragLeave={event => { if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setDragging(false); }} onDrop={event => { event.preventDefault(); setDragging(false); void upload(event.dataTransfer.files); }}>
              <button className={`drop-zone ${dragging ? "dragging" : ""}`} type="button" onClick={openFiles} disabled={Boolean(uploading)}>
                <span className="upload-icon-wrap">{uploading ? <LoaderCircle className="spin" size={22} /> : <UploadCloud size={22} />}</span><span className="drop-copy"><strong>{uploading ? "Processing documents…" : "Drop your files here"}</strong><span>{uploading || "or browse from your computer"}</span></span><span className="file-types"><span>PDF</span><span>TXT</span><span>Up to 10 MB</span></span>
              </button>
              {(uploading || uploadNote) && <p className="upload-note" role="status">{uploading || uploadNote}</p>}
            </section>
            <section className="documents-section" aria-labelledby="documents-title">
              <div className="section-head"><div><h2 id="documents-title">{activeCollection?.name ?? "Your documents"} <span className="count-badge">{scope.length}</span></h2><p>Select files to narrow the search.</p></div>
                {activeCollection ? <div className="collection-actions"><button className="text-button" onClick={() => openPanel({ type: "rename", collection: activeCollection }, activeCollection.name)}>Rename</button>{activeCollection.document_count === 0 && <button className="text-button" onClick={() => openPanel({ type: "delete-collection", collection: activeCollection })}>Delete collection</button>}</div> :
                  view === "workspace" && <button className="text-button" onClick={() => navigate("documents")}>View all <ArrowUp size={13} className="arrow-diag" /></button>}
              </div>
              <label className="document-filter"><Search size={16} /><input type="search" aria-label="Filter documents by filename" placeholder="Filter by filename" value={filenameFilter} onChange={event => setFilenameFilter(event.target.value)} /></label>
              {displayed.length ? <div className="document-list">{displayed.map(doc => <div className={`document-row ${selectedInScope.includes(doc.id) ? "chosen" : ""}`} key={doc.id}>
                <label className="select-wrap"><input type="checkbox" checked={selectedInScope.includes(doc.id)} aria-label={`Include ${doc.filename} in search`} onChange={event => setSelected(ids => event.target.checked ? [...ids, doc.id] : ids.filter(id => id !== doc.id))} /></label>
                <FileGlyph type={doc.file_type} /><button className="document-info" onClick={() => openPanel({ type: "document", id: doc.id })}><strong title={doc.filename}>{doc.filename}</strong><span>{timeLabel(doc.created_at)}{doc.size_bytes !== null ? ` · ${sizeLabel(doc.size_bytes)}` : ""} · {doc.status === "ready" ? "Ready" : doc.status}</span></button>
                <button className="icon-btn delete-btn" aria-label={`Delete ${doc.filename}`} onClick={() => openPanel({ type: "delete-document", document: doc })}><Trash2 size={16} /></button>
              </div>)}</div> : <div className="empty-docs"><div className="empty-doc-icon"><BookOpen size={20} /></div><strong>{!loaded ? "Documents not loaded yet" : filenameFilter.trim() ? "No matching filenames" : activeCollection ? "This collection is empty" : "No documents yet"}</strong>
                <span>{!loaded ? "Check the backend connection if this persists." : filenameFilter.trim() ? "Try a different filename." : activeCollection ? "Open a document to assign it here." : "Upload a PDF or TXT file to begin."}</span>
                {loaded && (filenameFilter.trim() ? <button onClick={() => setFilenameFilter("")}>Clear filter</button> : activeCollection ? <button onClick={() => navigate("documents")}>Open all documents</button> : <button onClick={openFiles} disabled={Boolean(uploading)}>Upload your first document</button>)}
              </div>}
            </section>
            <div className="privacy-note"><ShieldCheck size={16} /><span>Local mode keeps document text on this machine.</span><button className="icon-btn" aria-label="Privacy information" onClick={help}><HelpCircle size={16} /></button></div>
          </div>
          <section className="chat-card" aria-labelledby="search-title">
            <header className="chat-header"><div className="assistant-avatar"><Search size={17} /></div><div className="chat-title"><h2 id="search-title">{useProvider ? "Ask with OpenAI" : "Local Document Search"}</h2><span>{useProvider ? "Optional generative answers" : "Ranked passages from your files"}</span></div>{messages.length > 0 && <button className="text-button" onClick={() => setMessages([])} disabled={busy}>Clear results</button>}</header>
            <form className="chat-compose" onSubmit={ask}><label htmlFor="question">Question or keywords</label><div className="compose-box"><textarea id="question" ref={questionRef} placeholder={scope.length ? "What are the main requirements?" : "Add a document to this search scope first"} value={question} maxLength={2000} rows={1} onChange={event => setQuestion(event.target.value)} onKeyDown={event => {
              if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) { event.preventDefault(); event.currentTarget.form?.requestSubmit(); }
            }} /><button className="send-button" type="submit" aria-label="Search documents" disabled={!question.trim() || busy || !scope.length}>{busy ? <LoaderCircle className="spin" size={17} /> : <Send size={17} />}</button></div>
              <div className="compose-meta"><span>{selectedInScope.length ? `${selectedInScope.length} selected` : `All ${scope.length} in ${activeCollection ? "this collection" : "workspace"}`}</span>{health?.ai_configured && <label className="provider-toggle"><input type="checkbox" checked={provider} onChange={event => setProvider(event.target.checked)} /> Use OpenAI</label>}<span>{useProvider ? "Provider mode" : "Extractive only"}</span></div>
            </form>
            <div className="chat-body" ref={resultsRef} aria-live="polite" tabIndex={messages.length ? 0 : undefined} aria-label="Search results">
              {!messages.length ? <div className="chat-empty"><div className="assistant-orbit" aria-hidden="true"><div className="orbit-ring ring-one" /><div className="orbit-ring ring-two" /><span><Search size={21} /></span><i className="orbit-dot dot-one" /><i className="orbit-dot dot-two" /><i className="orbit-dot dot-three" /></div>
                <div className="chat-empty-copy"><h3>Find a passage in your documents</h3><p>Search for a term, phrase, or question. Try words likely to appear in the source.</p></div>
                <div className="suggestions">{["requirements", "deadlines", "next steps"].map(term => <button key={term} disabled={!scope.length} onClick={() => { setQuestion(term); questionRef.current?.focus(); }}><span>TRY SEARCHING</span><strong>{term}</strong><ArrowUp size={14} className="suggestion-arrow" /></button>)}</div>
              </div> : <div className="messages">{messages.map((message, index) => <article className="search-result" key={index}>
                <p className="search-query"><Search size={15} /> <strong>{message.query}</strong></p>
                {message.error && <p className="search-error">{message.error}</p>}
                {message.result && <><p className="message-role">{message.result.mode === "generative" ? "OPENAI ANSWER" : "LOCAL RETRIEVAL"}</p>
                  {message.result.answer && <p className="answer">{message.result.answer}</p>}
                  {!!message.result.sources.length && <ol className="citations">{message.result.sources.map(source => <li key={source.passage_id}><button className="source-link" onClick={() => showSource(source)}><FileText size={15} /><span>{source.filename}</span><b>{source.filename.toLowerCase().endsWith(".pdf") ? `Page ${source.page_number}` : "Text file"}</b></button><blockquote>{source.excerpt}</blockquote></li>)}</ol>}
                </>}
              </article>)}{busy && <p className="loading-results"><LoaderCircle className="spin" size={16} /> Searching documents…</p>}</div>}
            </div>

          </section>
        </div>
        <footer className="footer"><span>DOCUMIND <i>·</i> YOUR DOCUMENTS, WITH ANSWERS</span><span>Open a citation to read the source passage.</span></footer>
      </div>
    </main>
    {panel && <Modal title={modalTitle} close={closePanel} className={panel.type === "document" ? "detail-modal" : ""}>
      {panel.type === "help" ? <div className="modal-content help-copy"><p><strong>1. Upload</strong> a PDF with selectable text or a UTF-8 TXT file. DocuMind extracts and indexes it on this machine.</p><p><strong>2. Search</strong> using words likely to appear in the document. Select files or open a collection to narrow the search. Click any citation to jump to the matching extracted passage.</p><p><strong>3. Organize</strong> with the plus button beside Collections. Open a document to assign or move it.</p><p>Local search returns excerpts without generating text. Scanned pages require OCR before uploading. Documents expire after the configured retention period. This browser workspace has no sign-in and is intended for local use.</p></div> :
        panel.type === "document" ? <div className="modal-content detail-content">
          {panelError && <p className="search-error" role="alert">{panelError}</p>}
          {!detail && !panelError && <p role="status">Loading extracted text…</p>}
          {detail && <><div className="detail-meta"><span>{detail.document.file_type.toUpperCase()} · {timeLabel(detail.document.created_at)}{detail.document.size_bytes !== null ? ` · ${sizeLabel(detail.document.size_bytes)}` : ""} · {detail.passages.length} passages</span><label>Collection <select value={detail.document.collection_id ?? ""} disabled={saving} onChange={event => void assign(detail.document, event.target.value)}><option value="">Unfiled</option>{collections.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label></div>
            <h3>Extracted text</h3><p className="detail-hint">Passages may overlap so search results retain their context.</p>
            {detail.passages.map((passage, index) => <section key={passage.passage_id} id={`passage-${passage.passage_id}`} tabIndex={panel.passage === passage.passage_id ? -1 : undefined} className={`passage ${panel.passage === passage.passage_id ? "highlighted" : ""}`}><h4>{detail.document.file_type === "pdf" ? `Page ${passage.page_number} · ` : ""}Passage {index + 1}</h4><p>{passage.text}</p></section>)}</>}
        </div> :
        <form className="modal-content" onSubmit={submitPanel}>
          {panel.type === "delete-document" ? <p>Delete <strong>{panel.document.filename}</strong> and its indexed passages? This cannot be undone.</p> :
            panel.type === "delete-collection" ? <p>Delete the empty collection <strong>{panel.collection.name}</strong>?</p> :
              <label className="field-label">{panel.type === "settings" ? "Display name" : "Collection name"}<input value={draft} onChange={event => setDraft(event.target.value)} maxLength={panel.type === "settings" ? 40 : 60} required={panel.type !== "settings"} autoFocus /></label>}
          {panel.type === "settings" && <p className="detail-hint">This name is saved in this browser. There is no signed-in account.</p>}
          {panelError && <p className="search-error" role="alert">{panelError}</p>}
          <div className="modal-actions"><button type="button" className="button-secondary" disabled={saving} onClick={closePanel}>Cancel</button><button type="submit" className={panel.type.startsWith("delete") ? "primary-button danger" : "primary-button"} disabled={saving}>{saving ? "Saving…" : panel.type.startsWith("delete") ? "Delete" : panel.type === "create" ? "Create collection" : "Save"}</button></div>
        </form>}
    </Modal>}
  </div>;
}
