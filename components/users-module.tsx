"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { getApiUrl } from "@/lib/api";
import {
  Check,
  FileUp,
  MapPinned,
  Pencil,
  Plus,
  RefreshCw,
  Search,
  ShieldCheck,
  Trash2,
  UserPlus,
  Users,
  X,
} from "lucide-react";

const API_URL = getApiUrl();

type AdminUser = {
  id: string;
  email: string;
  full_name: string;
  is_active: boolean;
  roles: string[];
  authorized_area_ids: string[];
};

type AuthorizedArea = {
  id: string;
  name: string;
  description: string | null;
  original_filename: string | null;
  is_active: boolean;
};

type UserForm = {
  id: string | null;
  full_name: string;
  email: string;
  password: string;
  role: "ADMINISTRADOR" | "ANALISTA";
  is_active: boolean;
  areaIds: string[];
};

const EMPTY_FORM: UserForm = {
  id: null,
  full_name: "",
  email: "",
  password: "",
  role: "ANALISTA",
  is_active: true,
  areaIds: [],
};

function getInitials(name: string) {
  return name
    .trim()
    .split(/\s+/)
    .slice(0, 2)
    .map((part) => part[0] ?? "")
    .join("")
    .toUpperCase();
}

export function UsersModule() {
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [areas, setAreas] = useState<AuthorizedArea[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [uploadingArea, setUploadingArea] = useState(false);
  const [search, setSearch] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [editorOpen, setEditorOpen] = useState(false);
  const [areasOpen, setAreasOpen] = useState(false);
  const [form, setForm] = useState<UserForm>(EMPTY_FORM);

  const [areaName, setAreaName] = useState("");
  const [areaDescription, setAreaDescription] = useState("");
  const [areaFile, setAreaFile] = useState<File | null>(null);

  const loadData = async () => {
    setLoading(true);
    setError(null);

    try {
      const [usersResponse, areasResponse] = await Promise.all([
        fetch(`${API_URL}/users`, {
          credentials: "include",
        }),
        fetch(`${API_URL}/security/authorized-areas`, {
          credentials: "include",
        }),
      ]);

      if (!usersResponse.ok) {
        throw new Error("Não foi possível carregar os usuários.");
      }

      if (!areasResponse.ok) {
        throw new Error("Não foi possível carregar as áreas autorizadas.");
      }

      const [usersPayload, areasPayload] = await Promise.all([
        usersResponse.json(),
        areasResponse.json(),
      ]);

      setUsers(usersPayload);
      setAreas(areasPayload);
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : "Falha ao carregar a administração de usuários.",
      );
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadData();
  }, []);

  const filteredUsers = useMemo(() => {
    const normalized = search.trim().toLowerCase();

    if (!normalized) return users;

    return users.filter((user) =>
      `${user.full_name} ${user.email} ${user.roles.join(" ")}`
        .toLowerCase()
        .includes(normalized),
    );
  }, [users, search]);

  const openNewUser = () => {
    setForm(EMPTY_FORM);
    setMessage(null);
    setError(null);
    setEditorOpen(true);
  };

  const openEditUser = (user: AdminUser) => {
    setForm({
      id: user.id,
      full_name: user.full_name,
      email: user.email,
      password: "",
      role: user.roles.includes("ADMINISTRADOR")
        ? "ADMINISTRADOR"
        : "ANALISTA",
      is_active: user.is_active,
      areaIds: user.authorized_area_ids,
    });

    setMessage(null);
    setError(null);
    setEditorOpen(true);
  };

  const toggleArea = (areaId: string, checked: boolean) => {
    setForm((current) => ({
      ...current,
      areaIds: checked
        ? Array.from(new Set([...current.areaIds, areaId]))
        : current.areaIds.filter((id) => id !== areaId),
    }));
  };

  const saveUser = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setSaving(true);
    setError(null);
    setMessage(null);

    try {
      const isEditing = Boolean(form.id);

      const payload: Record<string, unknown> = {
        email: form.email.trim(),
        full_name: form.full_name.trim(),
        role: form.role,
        is_active: form.is_active,
      };

      if (form.password.trim()) {
        payload.password = form.password;
      }

      if (!isEditing && !form.password.trim()) {
        throw new Error("Informe uma senha para o novo usuário.");
      }

      const response = await fetch(
        isEditing ? `${API_URL}/users/${form.id}` : `${API_URL}/users`,
        {
          method: isEditing ? "PATCH" : "POST",
          credentials: "include",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        },
      );

      const body = await response.json().catch(() => null);

      if (!response.ok) {
        throw new Error(
          typeof body?.detail === "string"
            ? body.detail
            : "Não foi possível salvar o usuário.",
        );
      }

      const savedUser = body as AdminUser;

      if (form.role === "ANALISTA") {
        const areaResponse = await fetch(
          `${API_URL}/users/${savedUser.id}/authorized-areas`,
          {
            method: "PUT",
            credentials: "include",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              area_ids: form.areaIds,
            }),
          },
        );

        const areaBody = await areaResponse.json().catch(() => null);

        if (!areaResponse.ok) {
          throw new Error(
            typeof areaBody?.detail === "string"
              ? areaBody.detail
              : "Usuário salvo, mas não foi possível atualizar as áreas autorizadas.",
          );
        }
      }

      setMessage(
        isEditing
          ? "Usuário atualizado com sucesso."
          : "Usuário criado com sucesso.",
      );

      setEditorOpen(false);
      await loadData();
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : "Não foi possível salvar o usuário.",
      );
    } finally {
      setSaving(false);
    }
  };

  const uploadArea = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();

    if (!areaFile) {
      setError("Selecione um arquivo KML.");
      return;
    }

    setUploadingArea(true);
    setError(null);
    setMessage(null);

    try {
      const body = new FormData();
      body.append("name", areaName.trim());
      body.append("description", areaDescription.trim());
      body.append("file", areaFile);

      const response = await fetch(
        `${API_URL}/security/authorized-areas`,
        {
          method: "POST",
          credentials: "include",
          body,
        },
      );

      const payload = await response.json().catch(() => null);

      if (!response.ok) {
        throw new Error(
          typeof payload?.detail === "string"
            ? payload.detail
            : "Não foi possível importar o KML.",
        );
      }

      setAreaName("");
      setAreaDescription("");
      setAreaFile(null);
      setMessage("Área autorizada importada com sucesso.");
      await loadData();
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : "Não foi possível importar a área.",
      );
    } finally {
      setUploadingArea(false);
    }
  };

  const setAreaActive = async (
    area: AuthorizedArea,
    isActive: boolean,
  ) => {
    setError(null);
    setMessage(null);

    try {
      const response = await fetch(
        `${API_URL}/security/authorized-areas/${area.id}`,
        {
          method: "PATCH",
          credentials: "include",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            is_active: isActive,
          }),
        },
      );

      const body = await response.json().catch(() => null);

      if (!response.ok) {
        throw new Error(
          typeof body?.detail === "string"
            ? body.detail
            : "Não foi possível alterar a área.",
        );
      }

      setMessage(
        isActive ? "Área ativada." : "Área desativada.",
      );

      await loadData();
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : "Falha ao alterar a área.",
      );
    }
  };

  const deleteUser = async (user: AdminUser) => {
    if (!window.confirm(`Excluir definitivamente o usuário "${user.full_name}"? Esta ação não pode ser desfeita.`)) return;
    setError(null);
    setMessage(null);
    try {
      const response = await fetch(`${API_URL}/users/${user.id}`, {
        method: "DELETE",
        credentials: "include",
      });
      const body = response.status === 204 ? null : await response.json().catch(() => null);
      if (!response.ok) {
        throw new Error(
          typeof body?.detail === "string" ? body.detail : "Não foi possível excluir o usuário.",
        );
      }
      setMessage("Usuário excluído com sucesso.");
      await loadData();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Falha ao excluir usuário.");
    }
  };

  const deleteArea = async (area: AuthorizedArea) => {
    if (!window.confirm(`Excluir definitivamente a área autorizada "${area.name}"? Os vínculos com usuários também serão removidos.`)) return;
    setError(null);
    setMessage(null);
    try {
      const response = await fetch(`${API_URL}/security/authorized-areas/${area.id}`, {
        method: "DELETE",
        credentials: "include",
      });
      const body = response.status === 204 ? null : await response.json().catch(() => null);
      if (!response.ok) {
        throw new Error(
          typeof body?.detail === "string" ? body.detail : "Não foi possível excluir a área.",
        );
      }
      setMessage("Área autorizada excluída com sucesso.");
      await loadData();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Falha ao excluir área.");
    }
  };

  return (
    <section className="users-module">
      <header className="users-hero">
        <div>
          <p className="eyebrow">ADMINISTRAÇÃO</p>
          <h2>Usuários e acessos territoriais</h2>
          <p>
            Gerencie contas, perfis e as áreas onde cada analista
            pode utilizar o sistema.
          </p>
        </div>

        <div className="users-hero-actions">
          <button
            type="button"
            className="users-secondary-button"
            onClick={() => setAreasOpen(true)}
          >
            <MapPinned size={17} />
            Áreas autorizadas
          </button>

          <Button onClick={openNewUser}>
            <UserPlus size={17} />
            Novo usuário
          </Button>
        </div>
      </header>

      <div className="users-summary">
        <article>
          <small>Usuários</small>
          <strong>{users.length}</strong>
        </article>

        <article>
          <small>Analistas ativos</small>
          <strong>
            {
              users.filter(
                (user) =>
                  user.is_active &&
                  user.roles.includes("ANALISTA"),
              ).length
            }
          </strong>
        </article>

        <article>
          <small>Áreas autorizadas</small>
          <strong>
            {areas.filter((area) => area.is_active).length}
          </strong>
        </article>
      </div>

      {message && (
        <div className="users-message success">
          <Check size={17} />
          {message}
        </div>
      )}

      {error && (
        <div className="users-message error">
          <X size={17} />
          {error}
        </div>
      )}

      <div className="users-toolbar">
        <label className="users-search">
          <Search size={17} />
          <input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Buscar por nome, e-mail ou perfil"
          />
        </label>

        <button
          type="button"
          className="users-refresh"
          onClick={() => void loadData()}
          disabled={loading}
        >
          <RefreshCw size={16} />
          Atualizar
        </button>
      </div>

      <div className="users-table-card">
        <div className="users-table-head">
          <span>Usuário</span>
          <span>Perfil</span>
          <span>Status</span>
          <span>Áreas</span>
          <span />
        </div>

        {loading ? (
          <div className="users-empty">Carregando usuários…</div>
        ) : filteredUsers.length === 0 ? (
          <div className="users-empty">
            Nenhum usuário encontrado.
          </div>
        ) : (
          filteredUsers.map((user) => {
            const role = user.roles.includes("ADMINISTRADOR")
              ? "ADMINISTRADOR"
              : "ANALISTA";

            return (
              <div className="users-table-row" key={user.id}>
                <div className="users-user-cell">
                  <span className="users-avatar">
                    {getInitials(user.full_name)}
                  </span>

                  <div>
                    <strong>{user.full_name}</strong>
                    <small>{user.email}</small>
                  </div>
                </div>

                <span
                  className={`users-role ${
                    role === "ADMINISTRADOR"
                      ? "administrator"
                      : "analyst"
                  }`}
                >
                  {role}
                </span>

                <span
                  className={`users-status ${
                    user.is_active ? "active" : "inactive"
                  }`}
                >
                  {user.is_active ? "Ativo" : "Inativo"}
                </span>

                <span className="users-area-count">
                  {role === "ADMINISTRADOR"
                    ? "Sem restrição"
                    : `${user.authorized_area_ids.length} área${
                        user.authorized_area_ids.length === 1
                          ? ""
                          : "s"
                      }`}
                </span>

                <div className="users-row-actions">
                  <button
                    type="button"
                    className="users-edit-button"
                    onClick={() => openEditUser(user)}
                  >
                    <Pencil size={16} />
                    Editar
                  </button>
                  <button
                    type="button"
                    className="users-delete-button"
                    onClick={() => void deleteUser(user)}
                    title="Excluir usuário"
                  >
                    <Trash2 size={16} />
                    Excluir
                  </button>
                </div>
              </div>
            );
          })
        )}
      </div>

      {editorOpen && (
        <div className="users-modal-backdrop">
          <section className="users-modal">
            <header>
              <div>
                <p className="eyebrow">
                  {form.id ? "EDITAR USUÁRIO" : "NOVO USUÁRIO"}
                </p>
                <h3>
                  {form.id
                    ? "Configurações da conta"
                    : "Cadastrar acesso"}
                </h3>
              </div>

              <button
                type="button"
                className="users-close-button"
                onClick={() => setEditorOpen(false)}
              >
                <X size={20} />
              </button>
            </header>

            <form onSubmit={saveUser}>
              <div className="users-form-grid">
                <label className="wide">
                  <span>Nome completo</span>
                  <input
                    value={form.full_name}
                    onChange={(event) =>
                      setForm((current) => ({
                        ...current,
                        full_name: event.target.value,
                      }))
                    }
                    required
                  />
                </label>

                <label className="wide">
                  <span>E-mail</span>
                  <input
                    type="email"
                    value={form.email}
                    onChange={(event) =>
                      setForm((current) => ({
                        ...current,
                        email: event.target.value,
                      }))
                    }
                    required
                  />
                </label>

                <label>
                  <span>Perfil</span>
                  <select
                    value={form.role}
                    onChange={(event) =>
                      setForm((current) => ({
                        ...current,
                        role: event.target.value as
                          | "ADMINISTRADOR"
                          | "ANALISTA",
                        areaIds:
                          event.target.value === "ADMINISTRADOR"
                            ? []
                            : current.areaIds,
                      }))
                    }
                  >
                    <option value="ANALISTA">ANALISTA</option>
                    <option value="ADMINISTRADOR">
                      ADMINISTRADOR
                    </option>
                  </select>
                </label>

                <label>
                  <span>
                    {form.id
                      ? "Nova senha (opcional)"
                      : "Senha inicial"}
                  </span>
                  <input
                    type="password"
                    value={form.password}
                    onChange={(event) =>
                      setForm((current) => ({
                        ...current,
                        password: event.target.value,
                      }))
                    }
                    minLength={12}
                    required={!form.id}
                  />
                </label>
              </div>

              <label className="users-active-field">
                <div>
                  <strong>Usuário ativo</strong>
                  <small>
                    Contas inativas não conseguem iniciar sessão.
                  </small>
                </div>

                <Switch
                  checked={form.is_active}
                  onCheckedChange={(checked) =>
                    setForm((current) => ({
                      ...current,
                      is_active: checked,
                    }))
                  }
                />
              </label>

              {form.role === "ANALISTA" ? (
                <section className="users-area-selector">
                  <div className="users-section-heading">
                    <div>
                      <strong>Restrições territoriais</strong>
                      <small>
                        O analista só poderá acessar o sistema
                        fisicamente dentro das áreas marcadas.
                      </small>
                    </div>

                    <ShieldCheck size={20} />
                  </div>

                  <div className="users-area-options">
                    {areas.length === 0 ? (
                      <p>Nenhuma área cadastrada.</p>
                    ) : (
                      areas.map((area) => (
                        <label
                          key={area.id}
                          className={
                            area.is_active
                              ? ""
                              : "users-area-option-inactive"
                          }
                        >
                          <input
                            type="checkbox"
                            checked={form.areaIds.includes(area.id)}
                            disabled={!area.is_active}
                            onChange={(event) =>
                              toggleArea(
                                area.id,
                                event.target.checked,
                              )
                            }
                          />

                          <div>
                            <strong>{area.name}</strong>
                            <small>
                              {area.description ||
                                area.original_filename ||
                                "Área autorizada"}
                            </small>
                          </div>

                          <span>
                            {area.is_active ? "Ativa" : "Inativa"}
                          </span>
                        </label>
                      ))
                    )}
                  </div>
                </section>
              ) : (
                <div className="users-admin-access">
                  <ShieldCheck size={20} />
                  <div>
                    <strong>Sem restrição territorial</strong>
                    <small>
                      Administradores possuem acesso integral ao
                      sistema.
                    </small>
                  </div>
                </div>
              )}

              <footer className="users-modal-actions">
                <button
                  type="button"
                  onClick={() => setEditorOpen(false)}
                >
                  Cancelar
                </button>

                <Button type="submit" disabled={saving}>
                  {saving
                    ? "Salvando…"
                    : form.id
                      ? "Salvar alterações"
                      : "Criar usuário"}
                </Button>
              </footer>
            </form>
          </section>
        </div>
      )}

      {areasOpen && (
        <div className="users-modal-backdrop">
          <section className="users-modal users-areas-modal">
            <header>
              <div>
                <p className="eyebrow">CONTROLE TERRITORIAL</p>
                <h3>Áreas autorizadas</h3>
              </div>

              <button
                type="button"
                className="users-close-button"
                onClick={() => setAreasOpen(false)}
              >
                <X size={20} />
              </button>
            </header>

            <form
              className="users-area-upload"
              onSubmit={uploadArea}
            >
              <label>
                <span>Nome da área</span>
                <input
                  value={areaName}
                  onChange={(event) =>
                    setAreaName(event.target.value)
                  }
                  required
                />
              </label>

              <label>
                <span>Descrição</span>
                <input
                  value={areaDescription}
                  onChange={(event) =>
                    setAreaDescription(event.target.value)
                  }
                />
              </label>

              <label className="users-kml-field">
                <FileUp size={20} />
                <div>
                  <strong>
                    {areaFile
                      ? areaFile.name
                      : "Selecionar arquivo KML"}
                  </strong>
                  <small>
                    Polígono da área de utilização autorizada
                  </small>
                </div>

                <input
                  type="file"
                  accept=".kml,application/vnd.google-earth.kml+xml"
                  onChange={(event) =>
                    setAreaFile(event.target.files?.[0] ?? null)
                  }
                />
              </label>

              <Button
                type="submit"
                disabled={uploadingArea}
              >
                <Plus size={16} />
                {uploadingArea
                  ? "Importando…"
                  : "Importar área"}
              </Button>
            </form>

            <div className="users-area-list">
              {areas.map((area) => (
                <article key={area.id}>
                  <div>
                    <strong>{area.name}</strong>
                    <small>
                      {area.description ||
                        area.original_filename ||
                        "Sem descrição"}
                    </small>
                  </div>

                  <div className="users-area-actions">
                    <label>
                      <Switch
                        checked={area.is_active}
                        onCheckedChange={(checked) =>
                          void setAreaActive(area, checked)
                        }
                      />
                      <span>
                        {area.is_active ? "Ativa" : "Inativa"}
                      </span>
                    </label>
                    <button
                      type="button"
                      className="users-delete-button"
                      onClick={() => void deleteArea(area)}
                      title="Excluir área autorizada"
                    >
                      <Trash2 size={16} />
                      Excluir
                    </button>
                  </div>
                </article>
              ))}
            </div>
          </section>
        </div>
      )}
    </section>
  );
}
