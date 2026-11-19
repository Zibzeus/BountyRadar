import { useState, useEffect, FormEvent, ReactNode } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Activity,
  Bookmark,
  Clock,
  ExternalLink,
  FlaskConical,
  Plug,
  RefreshCw,
  Upload,
} from "lucide-react";
import { api, base, Data, date, label, url } from "./api";

function useList(route: string, poll = false) {
  return useQuery({
    queryKey: [route],
    queryFn: () => api(route),
    refetchInterval: poll ? 5000 : false,
  });
}
function format(v: unknown): string {
  if (v === null || v === undefined || v === "") return "Unknown";
  if (typeof v === "object") return JSON.stringify(v, null, 2);
  return String(v);
}
function Outcome({ value }: { value: string }) {
  return value ? (
    <div className="note" role="status">
      {value}
    </div>
  ) : null;
}
function Field({ title, children }: { title: string; children: ReactNode }) {
  return (
    <label>
      {title}
      {children}
    </label>
  );
}
function useAction() {
  const qc = useQueryClient(),
    [message, msg] = useState(""),
    [pending, busy] = useState(false);
  async function run(action: () => Promise<unknown>, success: string) {
    busy(true);
    msg("");
    try {
      await action();
      msg(success);
      await qc.invalidateQueries();
    } catch (e) {
      msg(e instanceof Error ? e.message : String(e));
    } finally {
      busy(false);
    }
  }
  return { run, pending, message };
}
function fields(e: FormEvent<HTMLFormElement>) {
  e.preventDefault();
  return Object.fromEntries(new FormData(e.currentTarget)) as Record<
    string,
    string
  >;
}
function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="panel">
      <h2>{title}</h2>
      {children}
    </section>
  );
}
function ListState({
  error,
  pending,
  empty,
}: {
  error: unknown;
  pending: boolean;
  empty: boolean;
}) {
  return (
    <Outcome
      value={
        error
          ? String(error)
          : pending
            ? "Loading…"
            : empty
              ? "No records yet."
              : ""
      }
    />
  );
}
export function Connections({ role }: { role: string }) {
  const list = useList("/connections"),
    a = useAction(),
    [edit, setEdit] = useState<Data | null>(null),
    [kind, provider] = useState("openai");
  const kinds = [
    "openai",
    "anthropic",
    "firecrawl",
    "agent_reach",
    "hackerone",
    "bugcrowd",
    "intigriti",
    "yeswehack",
  ];
  const rows: Data[] = list.data?.items || [];
  return (
    <>
      <Section title="Configured connections">
        <ListState
          error={list.error}
          pending={list.isPending}
          empty={!rows.length}
        />
        {rows.map((r) => (
          <div className="list-row" key={r.id}>
            <div>
              <b>{r.name}</b>
              <small>
                {label(r.kind)} · {r.team ? "Team" : "Personal"}
                {r.model ? " · " + r.model : ""}
              </small>
            </div>
            {role !== "viewer" && (
              <div className="actions">
                <button
                  disabled={a.pending}
                  onClick={() =>
                    a.run(
                      () => api("/connections/" + r.id + "/test", "POST"),
                      "Connection test passed.",
                    )
                  }
                >
                  Test
                </button>
                <button
                  onClick={() => {
                    setEdit(r);
                    provider(r.kind);
                  }}
                >
                  Edit
                </button>
                <button
                  disabled={a.pending}
                  onClick={() => {
                    if (confirm("Remove this connection?"))
                      a.run(
                        () => api("/connections/" + r.id, "DELETE"),
                        "Connection removed.",
                      );
                  }}
                >
                  Remove
                </button>
              </div>
            )}
          </div>
        ))}
      </Section>
      {role !== "viewer" && (
        <Section title={edit ? "Edit connection" : "Add connection"}>
          <form
            key={edit?.id || "new"}
            className="form"
            onSubmit={(e) => {
              const f = fields(e);
              a.run(async () => {
                const body: Data = {
                  name: f.name,
                  kind,
                  model: f.model || "",
                  endpoint: f.endpoint || "",
                  team: f.team === "on",
                };
                if (f.key || !edit) body.key = f.key || "";
                await api(
                  "/connections" + (edit ? "/" + edit.id : ""),
                  edit ? "PUT" : "POST",
                  body,
                );
                setEdit(null);
                provider("openai");
              }, "Connection saved.");
              e.currentTarget.querySelector<HTMLInputElement>(
                "input[name=key]",
              )!.value = "";
            }}
          >
            <Field title="Connection name">
              <input required name="name" defaultValue={edit?.name} />
            </Field>
            <Field title="Provider">
              <select value={kind} onChange={(e) => provider(e.target.value)}>
                {kinds.map((k) => (
                  <option key={k}>{k}</option>
                ))}
              </select>
            </Field>
            {["openai", "anthropic", "firecrawl", "agent_reach"].includes(
              kind,
            ) && (
              <Field title="API endpoint">
                <input
                  required
                  type="url"
                  name="endpoint"
                  placeholder="https://provider.example/v1"
                  defaultValue={edit?.endpoint}
                />
              </Field>
            )}
            {["openai", "anthropic", "hackerone", "bugcrowd"].includes(
              kind,
            ) && (
              <Field
                title={
                  ["openai", "anthropic"].includes(kind)
                    ? "Model ID"
                    : "API username"
                }
              >
                <input required name="model" defaultValue={edit?.model} />
              </Field>
            )}
            <Field
              title={
                edit
                  ? "Replacement API key (leave empty to keep current key)"
                  : "API key"
              }
            >
              <input type="password" name="key" autoComplete="new-password" />
            </Field>
            {role === "admin" && (
              <label className="check">
                <input
                  type="checkbox"
                  name="team"
                  defaultChecked={!!edit?.team}
                />{" "}
                Share connection with team
              </label>
            )}
            <div className="actions">
              <button disabled={a.pending} className="primary">
                <Plug size={16} /> Save connection
              </button>
              {edit && (
                <button
                  type="button"
                  onClick={() => {
                    setEdit(null);
                    provider("openai");
                  }}
                >
                  Cancel edit
                </button>
              )}
            </div>
          </form>
        </Section>
      )}
      <Outcome value={a.message} />
    </>
  );
}
function Jobs({
  path = "/jobs",
  research = false,
  writable = true,
}: {
  path?: string;
  research?: boolean;
  writable?: boolean;
}) {
  const list = useList(path, true),
    a = useAction(),
    rows: Data[] = list.data?.items || [];
  return (
    <Section title={research ? "Research history" : "Recent jobs"}>
      <ListState
        error={list.error}
        pending={list.isPending}
        empty={!rows.length}
      />
      {rows.map((r) => (
        <div className="list-row" key={r.id}>
          <div>
            <b>
              {label(r.kind)} · {label(r.state)}
            </b>
            <small>
              {r.source} · {date(r.started)}
            </small>
            <details>
              <summary>Run details</summary>
              <pre>{format(r.details)}</pre>
            </details>
          </div>
          <div className="actions">
            {writable &&
              research &&
              ["running", "queued", "pending"].includes(r.state) && (
                <button
                  onClick={() =>
                    a.run(
                      () => api("/jobs/" + r.id + "/cancel", "POST"),
                      "Cancellation requested.",
                    )
                  }
                >
                  Cancel
                </button>
              )}
            {research && writable && ["needs_review"].includes(r.state) && (
              <button
                onClick={() =>
                  a.run(
                    () => api("/research/" + r.id + "/review", "POST"),
                    "Review recorded.",
                  )
                }
              >
                Mark reviewed
              </button>
            )}
          </div>
        </div>
      ))}
      <Outcome value={a.message} />
    </Section>
  );
}
function Schedule() {
  const s = useList("/schedule"),
    a = useAction(),
    all = ["hackerone", "bugcrowd", "intigriti", "yeswehack", "diodb"].map(
      (x) => "dataset:" + x,
    );
  return (
    <Section title="Refresh schedule">
      {s.data ? (
        <form
          key={JSON.stringify(s.data)}
          className="form"
          onSubmit={(e) => {
            e.preventDefault();
            const data = new FormData(e.currentTarget);
            a.run(
              () =>
                api("/schedule", "PUT", {
                  sources: data.getAll("sources"),
                  interval_hours: Number(data.get("interval_hours")),
                  daily_research_limit: Number(data.get("quota")),
                }),
              "Schedule updated.",
            );
          }}
        >
          <div className="actions">
            {all.map((k) => (
              <label className="check" key={k}>
                <input
                  type="checkbox"
                  name="sources"
                  value={k}
                  defaultChecked={s.data.sources?.includes(k)}
                />
                {k.split(":")[1]}
              </label>
            ))}
          </div>
          <Field title="Interval in hours">
            <input
              name="interval_hours"
              type="number"
              min="1"
              required
              defaultValue={s.data.interval_hours || 24}
            />
          </Field>
          <Field title="Daily research runs per member">
            <input
              name="quota"
              type="number"
              min="0"
              max="500"
              required
              defaultValue={s.data.daily_research_limit ?? 20}
            />
          </Field>
          <button disabled={a.pending}>Save schedule and limits</button>
        </form>
      ) : (
        <ListState pending={s.isPending} error={s.error} empty={false} />
      )}
      <Outcome value={a.message} />
    </Section>
  );
}
function Import() {
  const a = useAction(),
    [draft, preview] = useState<Data | null>(null),
    [source, input] = useState("");
  return (
    <Section title="Import program records">
      <form
        className="form"
        onSubmit={(e) => {
          e.preventDefault();
          a.run(async () => {
            const records = JSON.parse(source);
            preview(
              await api("/imports/preview", "POST", {
                records: Array.isArray(records) ? records : records.records,
              }),
            );
          }, "Preview ready.");
        }}
      >
        <Field title="Records JSON">
          <textarea
            required
            rows={6}
            value={source}
            onChange={(e) => {
              input(e.target.value);
              preview(null);
            }}
            placeholder={
              '[{"external_id":"…","platform":"Independent","name":"…","url":"https://…"}]'
            }
          />
        </Field>
        <Field title="Or load a JSON file">
          <input
            type="file"
            accept=".json,application/json"
            onChange={async (e) => {
              const file = e.target.files?.[0];
              if (file) {
                input(await file.text());
                preview(null);
              }
            }}
          />
        </Field>
        <button disabled={a.pending}>
          <Upload size={14} /> Preview import
        </button>
      </form>
      {draft && (
        <div className="note">
          <b>{draft.items?.length} records ready</b>
          <pre>{format(draft.items?.slice(0, 3))}</pre>
          <button
            disabled={a.pending}
            onClick={() =>
              a.run(async () => {
                await api("/imports/" + draft.id + "/commit", "POST");
                preview(null);
                input("");
              }, "Records imported.")
            }
          >
            Commit import
          </button>
        </div>
      )}
      <Outcome value={a.message} />
    </Section>
  );
}
export function Sources({ role }: { role: string }) {
  const s = useList("/sources", true),
    links = useList("/connections"),
    a = useAction(),
    [selected, setSelected] = useState<Record<string, string>>({});
  const rows: Data[] = s.data?.items || [];
  return (
    <>
      <Section title="Source directory">
        <ListState error={s.error} pending={s.isPending} empty={!rows.length} />
        {rows.map((r) => {
          const connections: Data[] = (links.data?.items || []).filter(
            (x: Data) => x.kind === r.slug.split(":")[1],
          );
          const manual =
            String(r.mode).includes("manual") ||
            String(r.slug).startsWith("manual");
          return (
            <div key={r.slug} className="list-row">
              <div>
                <b>{r.name || r.slug}</b>
                <small>
                  {label(r.mode)} ·{" "}
                  {r.last_run ? label(r.last_run.state) : "No refresh recorded"}
                </small>
                {r.last_run?.details?.error && (
                  <small>{r.last_run.details.error}</small>
                )}
              </div>
              {role !== "viewer" && !manual && (
                <div className="actions">
                  {r.slug.startsWith("api:") && (
                    <select
                      aria-label={"Connection for " + r.name}
                      value={selected[r.slug] || ""}
                      onChange={(e) =>
                        setSelected({ ...selected, [r.slug]: e.target.value })
                      }
                    >
                      <option value="">Choose connection</option>
                      {connections.map((x) => (
                        <option value={x.id} key={x.id}>
                          {x.name}
                        </option>
                      ))}
                    </select>
                  )}
                  <button
                    disabled={
                      a.pending ||
                      (r.slug.startsWith("api:") && !selected[r.slug])
                    }
                    onClick={() =>
                      a.run(
                        () =>
                          api(
                            "/sources/" +
                              encodeURIComponent(r.slug) +
                              "/refresh" +
                              (selected[r.slug]
                                ? "?connection_id=" +
                                  encodeURIComponent(selected[r.slug])
                                : ""),
                            "POST",
                          ),
                        "Refresh requested.",
                      )
                    }
                  >
                    <RefreshCw size={14} /> Refresh
                  </button>
                </div>
              )}
            </div>
          );
        })}
        <Outcome value={a.message} />
      </Section>
      {role === "admin" && <Schedule />}
      {role !== "viewer" && <Import />}
      <Jobs writable={role !== "viewer"} />
    </>
  );
}
export function Research({ role, program }: { role: string; program: string }) {
  const cons = useList("/connections"),
    catalog = useList("/programs?page_size=200"),
    a = useAction(),
    [q, search] = useState(""),
    found = useList("/programs?page_size=100&q=" + encodeURIComponent(q)),
    [sel, select] = useState(program);
  const connections: Data[] = cons.data?.items || [],
    programs: Data[] = q ? found.data?.items || [] : catalog.data?.items || [];
  return (
    <>
      {role !== "viewer" && (
        <Section title="Research a program">
          <form
            className="form"
            onSubmit={(e) => {
              const f = fields(e);
              a.run(
                () =>
                  api("/research", "POST", {
                    program_id: sel,
                    llm_id: f.llm_id,
                    browser_id: f.browser_id || null,
                    daily: f.daily === "on",
                  }),
                "Research queued.",
              );
            }}
          >
            <Field title="Find program">
              <input
                value={q}
                onChange={(e) => search(e.target.value)}
                placeholder="Search by name"
              />
            </Field>
            <Field title="Program">
              <select
                required
                value={sel}
                onChange={(e) => select(e.target.value)}
              >
                <option value="">Select a program</option>
                {sel && !programs.some((p) => String(p.id) === sel) && (
                  <option value={sel}>{sel}</option>
                )}
                {programs.map((p) => (
                  <option value={p.id} key={p.id}>
                    {p.name} · {p.platform}
                  </option>
                ))}
              </select>
            </Field>
            <Field title="Language model">
              <select required name="llm_id">
                <option value="">Choose connection</option>
                {connections
                  .filter((x) => ["anthropic", "openai"].includes(x.kind))
                  .map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.name}
                    </option>
                  ))}
              </select>
            </Field>
            <Field title="Browsing connection">
              <select name="browser_id">
                <option value="">Use existing source evidence</option>
                {connections
                  .filter((x) => ["firecrawl", "agent_reach"].includes(x.kind))
                  .map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.name}
                    </option>
                  ))}
              </select>
            </Field>
            {role === "admin" && (
              <label className="check">
                <input name="daily" type="checkbox" /> Repeat daily
              </label>
            )}
            <button disabled={a.pending} className="primary">
              <FlaskConical size={16} /> Run research
            </button>
          </form>
          <Outcome value={a.message} />
        </Section>
      )}
      <Jobs research path="/research" writable={role !== "viewer"} />
    </>
  );
}
export function Changes({ open }: { open: (id: string) => void }) {
  const c = useList("/changes", true),
    rows: Data[] = c.data?.items || [];
  return (
    <Section title="Change history">
      <ListState error={c.error} pending={c.isPending} empty={!rows.length} />
      {rows.map((r, i) => (
        <div className="change" key={r.id || i}>
          <div className="list-row">
            <div>
              <button
                className="program-name"
                onClick={() => open(r.program_id)}
              >
                {r.name}
              </button>
              <small>
                {date(r.time)} · {r.source}
              </small>
            </div>
            <span className="pill">{label(r.verification)}</span>
          </div>
          <Diff changes={r.diff} />
        </div>
      ))}
    </Section>
  );
}
function Diff({ changes }: { changes: Data[] }) {
  return (
    <details>
      <summary>{changes?.length || 0} changes</summary>
      {(changes || []).map((d, i) => (
        <div key={i}>
          <strong>{label(d.field)}</strong>
          <div className="diff">
            <div>
              <small>Before</small>
              <pre>{format(d.before)}</pre>
            </div>
            <div>
              <small>After</small>
              <pre>{format(d.after)}</pre>
            </div>
          </div>
        </div>
      ))}
    </details>
  );
}
export function Settings({ role }: { role: string }) {
  const profile = useList("/profile"),
    a = useAction(),
    defaults = {
      interests: 30,
      complexity: 15,
      repositories: 15,
      bounty: 15,
      changes: 10,
      technology: 10,
      opportunities: 5,
    };
  return (
    <>
      <Section title="Scoring preferences">
        {profile.data ? (
          <form
            className="form"
            key={JSON.stringify(profile.data)}
            onSubmit={(e) => {
              const f = fields(e),
                tags = (s: string) =>
                  s
                    .split(",")
                    .map((i) => i.trim())
                    .filter(Boolean);
              a.run(
                () =>
                  api("/profile", "PUT", {
                    interests: tags(f.interests),
                    technologies: tags(f.technologies),
                    complexity: f.complexity,
                    weights: Object.fromEntries(
                      Object.keys(defaults).map((k) => [k, Number(f[k])]),
                    ),
                  }),
                "Preferences saved.",
              );
            }}
          >
            <Field title="Research interests, comma separated">
              <input
                name="interests"
                defaultValue={(profile.data.interests || []).join(", ")}
              />
            </Field>
            <Field title="Technologies, comma separated">
              <input
                name="technologies"
                defaultValue={(profile.data.technologies || []).join(", ")}
              />
            </Field>
            <Field title="Preferred scope">
              <select
                name="complexity"
                defaultValue={profile.data.complexity || "small"}
              >
                <option value="small">Smaller scope</option>
                <option value="large">Larger scope</option>
              </select>
            </Field>
            <div className="weight-grid">
              {Object.entries(defaults).map(([k, v]) => (
                <Field key={k} title={label(k) + " weight"}>
                  <input
                    type="number"
                    min="0"
                    max="100"
                    name={k}
                    required
                    defaultValue={profile.data.weights?.[k] ?? v}
                  />
                </Field>
              ))}
            </div>
            <button disabled={a.pending}>Save preferences</button>
          </form>
        ) : (
          <Outcome value={String(profile.error || "Loading…")} />
        )}
      </Section>
      {role === "admin" && <Members />}
      <Outcome value={a.message} />
    </>
  );
}
function Members() {
  const list = useList("/users"),
    a = useAction();
  return (
    <Section title="Workspace members">
      {(list.data?.items || []).map((r: Data) => (
        <div className="list-row" key={r.id}>
          <b>{r.username}</b>
          <span>{r.role}</span>
        </div>
      ))}
      <form
        className="form"
        onSubmit={(e) => {
          const f = fields(e);
          a.run(() => api("/users", "POST", f), "Member created.");
          e.currentTarget.reset();
        }}
      >
        <Field title="Username">
          <input name="username" required />
        </Field>
        <Field title="Password">
          <input
            type="password"
            name="password"
            minLength={12}
            required
            autoComplete="new-password"
          />
        </Field>
        <Field title="Role">
          <select name="role">
            <option>researcher</option>
            <option>viewer</option>
            <option>admin</option>
          </select>
        </Field>
        <button disabled={a.pending}>Create member</button>
      </form>
      <Outcome value={a.message} />
    </Section>
  );
}
export function DetailTools({
  id,
  p,
  writable,
  onResearch,
}: {
  id: string;
  p: Data;
  writable: boolean;
  onResearch: () => void;
}) {
  const a = useAction(),
    hist = useList("/programs/" + id + "/history"),
    marked = useList(
      "/programs?bookmarked=true&q=" +
        encodeURIComponent(p.name) +
        "&page_size=200",
    ),
    saved = !!marked.data?.items?.some((x: Data) => String(x.id) === id);
  const source = url(p.provenance?.url || p.source_url);
  return (
    <>
      <section className="panel">
        <div className="actions">
          <button
            disabled={a.pending || marked.isPending}
            onClick={() =>
              a.run(
                () =>
                  api(
                    "/programs/" + id + "/bookmark",
                    saved ? "DELETE" : "PUT",
                  ),
                saved ? "Bookmark removed." : "Bookmarked.",
              )
            }
          >
            <Bookmark size={15} />{" "}
            {saved ? "Remove bookmark" : "Bookmark program"}
          </button>
          {writable && (
            <button onClick={onResearch}>
              <FlaskConical size={15} /> Research program
            </button>
          )}
          {source && (
            <a className="link" href={source} target="_blank" rel="noreferrer">
              Source evidence <ExternalLink size={14} />
            </a>
          )}
        </div>
        <Outcome value={a.message} />
      </section>
      <Section title="Program intelligence">
        <dl>
          {[
            "verification",
            "reward",
            "out_of_scope",
              "reward_exclusions",
              "possibly_removed",
              "testing_restrictions",
            "disclosure_requirements",
            "safe_harbor",
            "technologies",
            "repositories",
            "ambiguities",
            "score",
            "score_breakdown",
            "acquired_at",
            "last_verified_at",
            "snapshot_id",
          ].map((k) => (
            <div className="dl-row" key={k}>
              <dt>{label(k)}</dt>
              <dd>
                <pre>{format(p[k])}</pre>
              </dd>
            </div>
          ))}
        </dl>
      </Section>
      <Section title="Snapshot history">
        {(hist.data?.items || []).map((r: Data, i: number) => (
          <div className="change" key={i}>
            <small>
              <Clock size={13} /> {date(r.time)} · {r.source} · {r.verification}
            </small>
            <Diff changes={r.diff} />
          </div>
        ))}
        <ListState
          error={hist.error}
          pending={hist.isPending}
          empty={!hist.data?.items?.length}
        />
      </Section>
      <Section title="Individual exports">
        <div className="actions">
          {[
            "PROGRAM_SCOPE.md",
            "PROGRAM_POLICY.md",
            "PROGRAM_METADATA.json",
            "SCOPE_RULES.json",
            "SCOPE_CHANGELOG.md",
          ].map((f) => (
            <a key={f} href={base + "/programs/" + id + "/export?file=" + f}>
              {f}
            </a>
          ))}
        </div>
      </Section>
    </>
  );
}
