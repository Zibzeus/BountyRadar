import React, { useState } from "react";
import { createRoot } from "react-dom/client";
import {
  QueryClient,
  QueryClientProvider,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import {
  Radar,
  Compass,
  LogOut,
  RefreshCw,
  Search,
  ChevronRight,
  ChevronLeft,
  ExternalLink,
  Download,
  Layers3,
  Database,
  Bookmark,
  SlidersHorizontal,
  BookOpen,
  ChevronsUpDown,
} from "lucide-react";
import { api, ApiError, base, Data, date, label, url } from "./api";
import {
  Changes,
  Connections,
  DetailTools,
  Research,
  Settings,
  Sources,
} from "./tools";
import { Activity, FlaskConical, Plug, Settings2, Rss } from "lucide-react";
import "./style.css";

const client = new QueryClient({
  defaultOptions: { queries: { retry: false, staleTime: 10000 } },
});
const platforms = [
  "HackerOne",
  "Bugcrowd",
  "Intigriti",
  "YesWeHack",
  "HackenProof",
  "Immunefi",
  "Code4rena",
  "Sherlock",
  "Cantina",
  "Independent",
];
function Brand() {
  return (
    <div className="brand">
      <Radar size={30} strokeWidth={1.8} />
      Bounty<span>Radar</span>
    </div>
  );
}
function Login({ success }: { success: () => void }) {
  const [err, error] = useState(""),
    [busy, setBusy] = useState(false);
  return (
    <main className="login">
      <div className="login-art">
        <Brand />
        <div className="radar-art" aria-hidden="true">
          <i />
          <i />
          <i />
          <i />
        </div>
        <div>
          <span className="eyebrow light">RESEARCH WORKSPACE</span>
          <h1>Program intelligence</h1>
          <p>Track public programs, scope changes and disclosure policies.</p>
        </div>
      </div>
      <form
        className="login-form"
        onSubmit={async (e) => {
          e.preventDefault();
          const f = new FormData(e.currentTarget);
          setBusy(true);
          error("");
          try {
            await api("/login", "POST", Object.fromEntries(f));
            success();
          } catch (ex) {
            error(String(ex));
          } finally {
            setBusy(false);
          }
        }}
      >
        <div className="eyebrow">BOUNTYRADAR</div>
        <h2>Workspace sign in</h2>
        <label>
          Username
          <input autoFocus required name="username" autoComplete="username" />
        </label>
        <label>
          Password
          <input
            required
            type="password"
            name="password"
            autoComplete="current-password"
          />
        </label>
        {err && (
          <div role="alert" className="error">
            {err}
          </div>
        )}
        <button className="primary" disabled={busy}>
          {busy ? "Signing in…" : "Sign in"}
        </button>
      </form>
    </main>
  );
}
export function Note({ children }: { children: React.ReactNode }) {
  return (
    <div className="note" role="status">
      {children}
    </div>
  );
}
export function Detail({
  id,
  back,
  writable,
  onResearch,
}: {
  id: string;
  back: () => void;
  writable: boolean;
  onResearch: () => void;
}) {
  const {
    data: p,
    error,
    isPending,
  } = useQuery({
    queryKey: ["detail", id],
    queryFn: () => api("/programs/" + encodeURIComponent(id)),
  });
  if (isPending || error || !p)
    return (
      <>
        <button onClick={back}>Back to directory</button>
        <Note>{error ? String(error) : "Loading program…"}</Note>
      </>
    );
  return (
    <>
      <button className="breadcrumb" onClick={back}>
        <ChevronLeft size={16} /> Program directory
      </button>
      <header>
        <div>
          <div className="eyebrow">{label(p.platform)}</div>
          <h1>{p.name}</h1>
          <span className="pill">{label(p.status)}</span>
        </div>
        <a
          className="primary"
          href={base + "/programs/" + encodeURIComponent(id) + "/export"}
        >
          <Download size={16} /> Export workspace
        </a>
      </header>
      <div className="detail-grid">
        <section className="panel">
          <h2>
            <Layers3 size={19} /> Program scope
          </h2>
          {(p.scope || []).length ? (
            <div className="rules">
              {p.scope.map((r: Data, i: number) => (
                <div key={i}>
                  <strong>{r.raw}</strong>
                  <small>
                    {label(r.kind)} · {label(r.effect)}
                  </small>
                </div>
              ))}
            </div>
          ) : (
            <Note>Scope is unknown.</Note>
          )}
        </section>
        <section className="panel">
          <h2>
            <BookOpen size={19} /> Program record
          </h2>
          <dl>
            {Object.entries({
              Platform: p.platform,
              Classification: p.kind,
              Source: p.source,
              Updated: date(p.updated_at),
              "Official verification": date(p.last_verified_at),
            }).map(([k, v]) => (
              <React.Fragment key={k}>
                <dt>{k}</dt>
                <dd>{label(v)}</dd>
              </React.Fragment>
            ))}
          </dl>
          {url(p.url) && (
            <a
              className="link"
              href={url(p.url)}
              target="_blank"
              rel="noreferrer"
            >
              Official program <ExternalLink size={14} />
            </a>
          )}
        </section>
      </div>
      <section className="panel">
        <h2>Original policy</h2>
        <pre>
          {p.policy || "Policy text unavailable. Consult the official program."}
        </pre>
      </section>
      <DetailTools id={id} p={p} writable={writable} onResearch={onResearch} />
    </>
  );
}
function App() {
  const qc = useQueryClient(),
    me = useQuery({ queryKey: ["me"], queryFn: () => api("/me") });
  const [view, nav] = useState("Discover"),
    [selected, select] = useState(""),
    [q, query] = useState(""),
    [platform, plat] = useState(""),
    [status, stat] = useState(""),
    [kind, type] = useState(""),
    [page, paginate] = useState(1),
    [sort, order] = useState("name"),
    [msg, message] = useState(""),
    [busy, setBusy] = useState(false);
  const [researchId, setResearchId] = useState("");
  const params = new URLSearchParams({
    q,
    platform,
    status,
    kind,
    page: String(page),
    page_size: "25",
    sort,
    ...(view === "Bookmarks" ? { bookmarked: "true" } : {}),
  });
  const programs = useQuery({
    queryKey: ["programs", params.toString()],
    queryFn: () => api("/programs?" + params),
    enabled: !!me.data,
    refetchInterval: 15000,
  });
  const refresh = async () => {
    setBusy(true);
    try {
      const result = await api("/sources/dataset:yeswehack/refresh", "POST");
      message(result.message || "Refresh requested.");
      await qc.invalidateQueries({ queryKey: ["programs"] });
    } catch (e) {
      message(String(e));
    } finally {
      setBusy(false);
    }
  };
  if (me.isPending) return <Note>Opening workspace…</Note>;
  if (me.error) {
    if (me.error instanceof ApiError && me.error.status === 401)
      return (
        <Login success={() => qc.invalidateQueries({ queryKey: ["me"] })} />
      );
    return (
      <Note>
        {String(me.error)} <button onClick={() => me.refetch()}>Retry</button>
      </Note>
    );
  }
  const user = me.data || {},
    p = programs.data,
    items: Data[] = p?.items || [],
    switchView = (s: string) => {
      nav(s);
      select("");
      paginate(1);
      message("");
    };
  return (
    <div className="shell">
      <a className="skip" href="#content">
        Skip to content
      </a>
      <aside>
        <Brand />
        <div className="nav-group">WORKSPACE</div>
        <nav aria-label="Workspace">
          {[
            [Compass, "Discover"],
            [Bookmark, "Bookmarks"],
            [Activity, "Changes"],
            [Rss, "Sources"],
            ...(user.role === "viewer"
              ? []
              : [
                  [FlaskConical, "Research"],
                  [Plug, "Connections"],
                ]),
            [Settings2, "Settings"],
          ].map(([I, n]) => {
            let Icon = I as typeof Compass;
            return (
              <button
                key={String(n)}
                aria-current={view === n ? "page" : undefined}
                className={view === n ? "active" : ""}
                onClick={() => switchView(String(n))}
              >
                <Icon size={18} />
                {String(n)}
              </button>
            );
          })}
        </nav>
        <div className="profile">
          <div className="avatar">
            {String(user.username || "U")
              .slice(0, 1)
              .toUpperCase()}
          </div>
          <div>
            <b>{user.username}</b>
            <small>{label(user.role)}</small>
          </div>
          <button
            title="Sign out"
            aria-label="Sign out"
            onClick={async () => {
              try {
                await api("/logout", "POST");
                select("");
                qc.clear();
                await me.refetch();
              } catch (e) {
                message(String(e));
              }
            }}
          >
            <LogOut size={16} />
          </button>
        </div>
      </aside>
      <main id="content" tabIndex={-1} className="workspace">
        <div className="top">
          <span>
            <Radar size={15} /> Workspace <ChevronRight size={13} />{" "}
            <b>{view}</b>
          </span>
          <span className="private">
            <i /> Self-hosted
          </span>
        </div>
        <article>
          {selected ? (
            <Detail
              id={selected}
              back={() => select("")}
              writable={user.role !== "viewer"}
              onResearch={() => {
                setResearchId(selected);
                switchView("Research");
              }}
            />
          ) : !["Discover", "Bookmarks"].includes(view) ? (
            <>
              <h1>{view}</h1>
              {view === "Sources" ? (
                <Sources role={user.role} />
              ) : view === "Connections" ? (
                <Connections role={user.role} />
              ) : view === "Research" ? (
                <Research role={user.role} program={researchId} />
              ) : view === "Changes" ? (
                <Changes open={select} />
              ) : (
                <Settings role={user.role} />
              )}
            </>
          ) : (
            <>
              <header>
                <div>
                  <h1>
                    {view === "Bookmarks"
                      ? "Saved programs"
                      : "Program directory"}
                  </h1>
                  <p>
                    {view === "Bookmarks"
                      ? "Your bookmarked programs."
                      : "Explore programs, compare scope and review source evidence."}
                  </p>
                </div>
                {user.role !== "viewer" && (
                  <button className="primary" disabled={busy} onClick={refresh}>
                    <RefreshCw size={16} />
                    {busy ? "Refreshing…" : "Refresh source"}
                  </button>
                )}
              </header>
              {msg && <Note>{msg}</Note>}
              <section className="catalog">
                <div className="catalog-title">
                  <h2>
                    <Database size={18} />{" "}
                    {view === "Bookmarks" ? "Bookmarks" : "Programs"}
                  </h2>
                  <span>{p?.total ?? "—"} results</span>
                </div>
                <div className="filters">
                  <label className="search">
                    <Search size={17} />
                    <input
                      aria-label="Search programs"
                      placeholder="Search programs…"
                      value={q}
                      onChange={(e) => {
                        query(e.target.value);
                        paginate(1);
                      }}
                    />
                  </label>
                  {[
                    [platform, plat, "Platform", platforms],
                    [status, stat, "Status", ["active", "paused", "unknown"]],
                    [
                      kind,
                      type,
                      "Type",
                      ["bug_bounty", "vdp", "contest", "unknown"],
                    ],
                  ].map(([value, setter, name, options]) => (
                    <select
                      key={String(name)}
                      aria-label={String(name)}
                      value={String(value)}
                      onChange={(e) => {
                        (setter as Function)(e.target.value);
                        paginate(1);
                      }}
                    >
                      <option value="">{String(name)}</option>
                      {(options as string[]).map((s) => (
                        <option key={s} value={s}>
                          {label(s)}
                        </option>
                      ))}
                    </select>
                  ))}
                  <label className="sort">
                    <SlidersHorizontal size={14} />
                    <select
                      aria-label="Sort programs"
                      value={sort}
                      onChange={(e) => {
                        order(e.target.value);
                        paginate(1);
                      }}
                    >
                      <option value="name">Name</option>
                      <option value="-updated_at">Updated</option>
                      <option value="-score">Score</option>
                    </select>
                  </label>
                </div>
                {programs.isPending ? (
                  <Note>Loading directory…</Note>
                ) : programs.error ? (
                  <Note>{String(programs.error)}</Note>
                ) : items.length ? (
                  <div
                    className="scroll"
                    role="region"
                    tabIndex={0}
                    aria-label="Program directory results"
                  >
                    <table>
                      <thead>
                        <tr>
                          <th scope="col">
                            Program <ChevronsUpDown size={12} />
                          </th>
                          <th scope="col">Platform</th>
                          <th scope="col">Status</th>
                          <th scope="col">Type</th>
                          <th scope="col">Fit score</th>
                          <th scope="col">Updated</th>
                          <th scope="col" aria-label="Inspect" />
                        </tr>
                      </thead>
                      <tbody>
                        {items.map((row) => (
                          <tr key={row.id}>
                            <th scope="row">
                              <button
                                className="program-name"
                                onClick={() => select(String(row.id))}
                              >
                                <span className="initial">
                                  {String(row.name).slice(0, 2).toUpperCase()}
                                </span>
                                {row.name}
                              </button>
                            </th>
                            <td data-label="Platform">{label(row.platform)}</td>
                            <td data-label="Status">
                              <span className={"pill " + row.status}>
                                {label(row.status)}
                              </span>
                            </td>
                            <td data-label="Type">{label(row.kind)}</td>
                            <td
                              data-label="Fit score"
                              title={JSON.stringify(row.contributions)}
                            >
                              {row.score} / 100
                            </td>
                            <td data-label="Updated">{date(row.updated_at)}</td>
                            <td>
                              <button
                                className="icon"
                                onClick={() => select(String(row.id))}
                                aria-label={"Inspect " + row.name}
                              >
                                <ChevronRight size={17} />
                              </button>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <div className="empty">
                    <Compass size={30} />
                    <h3>No matching programs</h3>
                    <p>
                      {q || platform || status || kind
                        ? "Adjust your search or filters."
                        : view === "Bookmarks"
                          ? "Bookmark a program to find it here."
                          : "Refresh a source to populate the directory."}
                    </p>
                  </div>
                )}
                <footer>
                  <span>Page {page}</span>
                  <div>
                    <button
                      disabled={page === 1}
                      onClick={() => paginate(page - 1)}
                    >
                      Previous
                    </button>
                    <button
                      disabled={
                        items.length === 0 ||
                        page * (p?.page_size || 25) >= (p?.total || 0)
                      }
                      onClick={() => paginate(page + 1)}
                    >
                      Next
                    </button>
                  </div>
                </footer>
              </section>
            </>
          )}
        </article>
      </main>
    </div>
  );
}
createRoot(document.getElementById("root")!).render(
  <QueryClientProvider client={client}>
    <App />
  </QueryClientProvider>,
);
