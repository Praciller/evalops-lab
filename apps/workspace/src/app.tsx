import { useCallback, useEffect, useReducer, useRef } from "react";
import {
  WorkspaceApiError,
  bootstrapSession,
  createWorkspace,
  getSession,
  listWorkspaces,
} from "./api/client";
import { WorkspaceSummary } from "./api/schemas";

// ─── State machine ────────────────────────────────────────────────────────────

type AuthState =
  | { status: "bootstrapping" }
  | { status: "unauthenticated"; error?: string }
  | { status: "authenticated" };

type WorkspaceState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "loaded"; workspaces: WorkspaceSummary[] }
  | { status: "error"; message: string };

type AppState = {
  auth: AuthState;
  workspaceState: WorkspaceState;
  createError: string | null;
  creating: boolean;
};

type AppAction =
  | { type: "AUTH_SUCCESS" }
  | { type: "AUTH_FAILURE"; error: string }
  | { type: "WORKSPACES_LOADING" }
  | { type: "WORKSPACES_LOADED"; workspaces: WorkspaceSummary[] }
  | { type: "WORKSPACES_ERROR"; message: string }
  | { type: "CREATE_START" }
  | { type: "CREATE_SUCCESS"; workspace: WorkspaceSummary }
  | { type: "CREATE_ERROR"; message: string }
  | { type: "CREATE_ERROR_CLEAR" };

function reducer(state: AppState, action: AppAction): AppState {
  switch (action.type) {
    case "AUTH_SUCCESS":
      return { ...state, auth: { status: "authenticated" } };
    case "AUTH_FAILURE":
      return {
        ...state,
        auth: { status: "unauthenticated", error: action.error },
      };
    case "WORKSPACES_LOADING":
      return { ...state, workspaceState: { status: "loading" } };
    case "WORKSPACES_LOADED":
      return {
        ...state,
        workspaceState: { status: "loaded", workspaces: action.workspaces },
      };
    case "WORKSPACES_ERROR":
      return {
        ...state,
        workspaceState: { status: "error", message: action.message },
      };
    case "CREATE_START":
      return { ...state, creating: true, createError: null };
    case "CREATE_SUCCESS": {
      const prev =
        state.workspaceState.status === "loaded"
          ? state.workspaceState.workspaces
          : [];
      return {
        ...state,
        creating: false,
        createError: null,
        workspaceState: {
          status: "loaded",
          workspaces: [...prev, action.workspace],
        },
      };
    }
    case "CREATE_ERROR":
      return { ...state, creating: false, createError: action.message };
    case "CREATE_ERROR_CLEAR":
      return { ...state, createError: null };
    default:
      return state;
  }
}

const initialState: AppState = {
  auth: { status: "bootstrapping" },
  workspaceState: { status: "idle" },
  createError: null,
  creating: false,
};

// ─── Bootstrap nonce extraction ───────────────────────────────────────────────

function extractAndClearNonce(): string | null {
  const hash = window.location.hash;
  const prefix = "#bootstrap=";
  if (!hash.startsWith(prefix)) return null;
  const nonce = hash.slice(prefix.length);
  // Immediately remove the fragment from browser history
  history.replaceState(null, "", window.location.pathname + window.location.search);
  return nonce || null;
}

// ─── App component ────────────────────────────────────────────────────────────

export default function App() {
  const [state, dispatch] = useReducer(reducer, initialState);
  const nameInputRef = useRef<HTMLInputElement>(null);
  const bootstrappedRef = useRef(false);

  // Bootstrap or check existing session
  useEffect(() => {
    if (bootstrappedRef.current) return;
    bootstrappedRef.current = true;

    async function boot() {
      const nonce = extractAndClearNonce();
      if (nonce) {
        try {
          await bootstrapSession(nonce);
          dispatch({ type: "AUTH_SUCCESS" });
        } catch (err) {
          const msg =
            err instanceof WorkspaceApiError
              ? err.message
              : "Authentication failed";
          dispatch({ type: "AUTH_FAILURE", error: msg });
        }
      } else {
        try {
          await getSession();
          dispatch({ type: "AUTH_SUCCESS" });
        } catch {
          dispatch({ type: "AUTH_FAILURE", error: "No bootstrap token found" });
        }
      }
    }

    void boot();
  }, []);

  // Load workspaces after authentication
  useEffect(() => {
    if (state.auth.status !== "authenticated") return;
    dispatch({ type: "WORKSPACES_LOADING" });
    listWorkspaces()
      .then((data) =>
        dispatch({ type: "WORKSPACES_LOADED", workspaces: data.workspaces })
      )
      .catch((err) => {
        const msg =
          err instanceof WorkspaceApiError
            ? err.message
            : "Failed to load workspaces";
        dispatch({ type: "WORKSPACES_ERROR", message: msg });
      });
  }, [state.auth.status]);

  const handleCreateWorkspace = useCallback(
    async (event: React.FormEvent<HTMLFormElement>) => {
      event.preventDefault();
      const name = nameInputRef.current?.value.trim() ?? "";
      if (!name) return;
      dispatch({ type: "CREATE_START" });
      try {
        const workspace = await createWorkspace(name);
        if (nameInputRef.current) nameInputRef.current.value = "";
        dispatch({ type: "CREATE_SUCCESS", workspace });
      } catch (err) {
        const msg =
          err instanceof WorkspaceApiError ? err.message : "Create failed";
        dispatch({ type: "CREATE_ERROR", message: msg });
      }
    },
    []
  );

  return (
    <main className="workspace-shell">
      {/* Local identity banner — must always be visible */}
      <div className="workspace-banner" role="status" aria-label="Local workspace indicator">
        <span className="workspace-banner-dot" aria-hidden="true" />
        <span>
          <strong>LOCAL WORKSPACE</strong> &mdash; Data stays on this machine
        </span>
      </div>

      <h1>EvalOps Evaluation Workspace</h1>
      <p className="subtitle">
        A private local environment for interactive retrieval evaluation.
        Results are stored on this machine only.
      </p>

      {state.auth.status === "bootstrapping" && (
        <p aria-live="polite" aria-busy="true">
          Starting session…
        </p>
      )}

      {state.auth.status === "unauthenticated" && (
        <section aria-label="Authentication required">
          <p className="error-message" role="alert">
            {state.auth.error ?? "Not authenticated"}
          </p>
        </section>
      )}

      {state.auth.status === "authenticated" && (
        <>
          <section aria-labelledby="workspace-section-heading">
            <h2 id="workspace-section-heading">Workspaces</h2>

            {state.workspaceState.status === "loading" && (
              <p aria-live="polite" aria-busy="true">
                Loading workspaces…
              </p>
            )}

            {state.workspaceState.status === "error" && (
              <p className="error-message" role="alert">
                {state.workspaceState.message}
              </p>
            )}

            {state.workspaceState.status === "loaded" && (
              <ul className="workspace-list" aria-label="Your workspaces">
                {state.workspaceState.workspaces.length === 0 ? (
                  <li className="empty-state">
                    No workspaces yet. Create one below.
                  </li>
                ) : (
                  state.workspaceState.workspaces.map((ws) => (
                    <li key={ws.workspace_id}>{ws.display_name}</li>
                  ))
                )}
              </ul>
            )}
          </section>

          <section
            className="surface"
            aria-labelledby="create-workspace-heading"
            style={{ marginTop: "var(--space-xl)" }}
          >
            <h2 id="create-workspace-heading">Create Workspace</h2>
            <form onSubmit={handleCreateWorkspace} noValidate>
              <label htmlFor="workspace-name">Workspace name</label>
              <input
                id="workspace-name"
                type="text"
                ref={nameInputRef}
                placeholder="e.g. Thai Retrieval v2"
                required
                autoComplete="off"
                aria-describedby={
                  state.createError ? "create-error" : undefined
                }
              />
              {state.createError && (
                <p
                  id="create-error"
                  className="error-message"
                  role="alert"
                >
                  {state.createError}
                </p>
              )}
              <button type="submit" disabled={state.creating}>
                {state.creating ? "Creating…" : "Create workspace"}
              </button>
            </form>
          </section>
        </>
      )}
    </main>
  );
}
