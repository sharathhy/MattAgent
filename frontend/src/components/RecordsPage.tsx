import { useQuery } from "@tanstack/react-query";
import { useState, type FormEvent, type ReactNode } from "react";

import { api, type Collection } from "../api/client";
import { ActionError, Empty, Field, PageHeader, Table, useAction, useCan } from "./kit";
import { ErrorState, Loading, Panel } from "./ui";

export interface FormField {
  name: string;
  label: string;
  type?: "text" | "textarea" | "number" | "date" | "select" | "checkbox";
  options?: string[];
  required?: boolean;
  placeholder?: string;
}

export interface Column<T> {
  label: string;
  render: (row: T) => ReactNode;
}

interface Props<T> {
  collection: Collection;
  eyebrow: string;
  title: string;
  intro?: ReactNode;
  fields: FormField[];
  columns: Column<T>[];
  empty: string;
  /** Turns form strings into the API body (numbers, nulls...). */
  toBody?: (values: Record<string, string | boolean>) => Record<string, unknown>;
  summary?: (rows: T[]) => ReactNode;
}

const initial = (fields: FormField[]) =>
  Object.fromEntries(
    fields.map((f) => [f.name, f.type === "checkbox" ? false : f.type === "select" ? (f.options?.[0] ?? "") : ""]),
  ) as Record<string, string | boolean>;

/** A page for a simple record collection: summary, add form, table with delete. */
export function RecordsPage<T extends { id: number }>(props: Props<T>) {
  const { collection, fields, columns } = props;
  const rows = useQuery({ queryKey: [collection], queryFn: () => api.list<T>(collection) });
  const canEdit = useCan("operator");
  const canDelete = useCan("admin");
  const [values, setValues] = useState(() => initial(fields));
  const create = useAction((body: Record<string, unknown>) => api.create<T>(collection, body), [[collection], ["dashboard"]]);
  const remove = useAction((id: number) => api.remove(collection, id), [[collection], ["dashboard"]]);

  function submit(e: FormEvent) {
    e.preventDefault();
    const cleaned = Object.fromEntries(Object.entries(values).map(([k, v]) => [k, v === "" ? null : v]));
    create.mutate(props.toBody ? props.toBody(values) : cleaned, { onSuccess: () => setValues(initial(fields)) });
  }

  return (
    <div className="space-y-5">
      <PageHeader eyebrow={props.eyebrow} title={props.title} />
      {props.intro && <p className="text-sm text-muted">{props.intro}</p>}
      {rows.data && props.summary?.(rows.data)}
      {canEdit && (
        <Panel title={`Add to ${props.title.toLowerCase()}`}>
          <form onSubmit={submit} className="grid gap-3 md:grid-cols-3">
            {fields.map((f) => (
              <div key={f.name} className={f.type === "textarea" ? "md:col-span-3" : ""}>
                <Field label={f.label}>
                  {f.type === "select" ? (
                    <select className="input" value={String(values[f.name])} onChange={(e) => setValues({ ...values, [f.name]: e.target.value })}>
                      {f.options?.map((o) => <option key={o} value={o}>{o.replace(/_/g, " ")}</option>)}
                    </select>
                  ) : f.type === "textarea" ? (
                    <textarea className="input min-h-24" required={f.required} placeholder={f.placeholder} value={String(values[f.name])}
                      onChange={(e) => setValues({ ...values, [f.name]: e.target.value })} />
                  ) : f.type === "checkbox" ? (
                    <input type="checkbox" className="h-4 w-4 accent-cyan-400" checked={Boolean(values[f.name])}
                      onChange={(e) => setValues({ ...values, [f.name]: e.target.checked })} />
                  ) : (
                    <input className="input" type={f.type ?? "text"} required={f.required} placeholder={f.placeholder}
                      step={f.type === "number" ? "0.01" : undefined} min={f.type === "number" ? 0 : undefined}
                      value={String(values[f.name])} onChange={(e) => setValues({ ...values, [f.name]: e.target.value })} />
                  )}
                </Field>
              </div>
            ))}
            <div className="md:col-span-3">
              <button type="submit" className="btn" disabled={create.isPending}>Save</button>
              <ActionError error={create.error} />
            </div>
          </form>
        </Panel>
      )}
      {rows.isPending && <Loading />}
      {rows.isError && <ErrorState error={rows.error} />}
      {rows.data?.length === 0 && <Empty>{props.empty}</Empty>}
      {rows.data && rows.data.length > 0 && (
        <Table head={[...columns.map((c) => c.label), ...(canDelete ? [""] : [])]}>
          {rows.data.map((row) => (
            <tr key={row.id} className="border-b border-line/50 align-top">
              {columns.map((c) => <td key={c.label} className="p-3">{c.render(row)}</td>)}
              {canDelete && (
                <td className="p-3 text-right">
                  <button type="button" className="text-xs text-muted hover:text-danger" onClick={() => remove.mutate(row.id)}>
                    Delete
                  </button>
                </td>
              )}
            </tr>
          ))}
        </Table>
      )}
      <ActionError error={remove.error} />
    </div>
  );
}
