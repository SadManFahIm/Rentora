import { useState } from "react";
import { Building2, FileText, Loader2, Plus, UserPlus } from "lucide-react";
import {
  useAddCorporateMembers,
  useBulkBooking,
  useCorporateAccounts,
  useCorporateInvoices,
  useCorporateMembers,
  useCreateCorporateAccount,
  useGenerateInvoice,
} from "../../hooks/useCorporate";
import { Button } from "../ui/button";
import { Input } from "../ui/input";
import { Skeleton } from "../ui/skeleton";
import { cn } from "../../lib/utils";

/** Corporate housing — company accounts, member invites, bulk bookings, invoices. */
export default function CorporatePanel() {
  const { data: accounts = [], isLoading: accountsLoading } = useCorporateAccounts();
  const { data: invoices = [] } = useCorporateInvoices();
  const create = useCreateCorporateAccount();
  const addMembers = useAddCorporateMembers();
  const bulk = useBulkBooking();
  const generate = useGenerateInvoice();

  const [showCreate, setShowCreate] = useState(false);
  const [createForm, setCreateForm] = useState({
    name: "",
    email: "",
    phone: "",
    address: "",
    vatNumber: "",
  });
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [inviteEmails, setInviteEmails] = useState("");
  const [bulkForm, setBulkForm] = useState({ roomId: "", members: "", from: "", to: "" });

  const { data: members = [] } = useCorporateMembers(selectedId);

  const submitCreate = () => {
    if (!createForm.name.trim() || !createForm.email.trim()) return;
    create.mutate(createForm, {
      onSuccess: () => {
        setShowCreate(false);
        setCreateForm({ name: "", email: "", phone: "", address: "", vatNumber: "" });
      },
    });
  };

  const submitInvite = () => {
    if (selectedId == null) return;
    const emails = inviteEmails
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);
    if (emails.length === 0) return;
    addMembers.mutate({ accountId: selectedId, emails }, { onSuccess: () => setInviteEmails("") });
  };

  const submitBulk = () => {
    const roomId = Number(bulkForm.roomId);
    const memberIds = bulkForm.members
      .split(",")
      .map((s) => Number(s.trim()))
      .filter((n) => Number.isFinite(n));
    if (!roomId || memberIds.length === 0 || !bulkForm.from || !bulkForm.to) return;
    bulk.mutate({
      roomId,
      memberIds,
      dateFrom: bulkForm.from,
      dateTo: bulkForm.to,
    });
  };

  if (accountsLoading) {
    return (
      <div className="flex flex-col gap-3">
        <Skeleton className="h-32 w-full rounded-2xl" />
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Building2 className="size-5 text-orange-600" />
          <div>
            <h2 className="font-display text-lg font-bold text-foreground">Corporate housing</h2>
            <p className="text-sm text-gray-600 dark:text-gray-400">
              Company accounts, member stays, bulk bookings and invoicing.
            </p>
          </div>
        </div>
        <Button
          className="bg-orange-600 text-white hover:bg-orange-700"
          onClick={() => setShowCreate((v) => !v)}
        >
          <Plus className="size-4" /> Create account
        </Button>
      </div>

      {showCreate && (
        <div className="grid max-w-lg grid-cols-1 gap-3 rounded-2xl border border-gray-200 bg-card p-5 dark:border-gray-800">
          <Input
            value={createForm.name}
            onChange={(e) => setCreateForm({ ...createForm, name: e.target.value })}
            placeholder="Company name"
          />
          <Input
            value={createForm.email}
            onChange={(e) => setCreateForm({ ...createForm, email: e.target.value })}
            placeholder="Billing email"
          />
          <Input
            value={createForm.phone}
            onChange={(e) => setCreateForm({ ...createForm, phone: e.target.value })}
            placeholder="Phone"
          />
          <Input
            value={createForm.address}
            onChange={(e) => setCreateForm({ ...createForm, address: e.target.value })}
            placeholder="Registered address"
          />
          <Input
            value={createForm.vatNumber}
            onChange={(e) => setCreateForm({ ...createForm, vatNumber: e.target.value })}
            placeholder="VAT / TIN number (optional)"
          />
          <Button
            className="bg-orange-600 text-white hover:bg-orange-700"
            disabled={create.isPending || !createForm.name.trim()}
            onClick={submitCreate}
          >
            {create.isPending ? <Loader2 className="size-4 animate-spin" /> : null} Create
          </Button>
        </div>
      )}

      {accounts.length === 0 && !showCreate ? (
        <p className="rounded-2xl border border-dashed border-gray-300 p-6 text-center text-sm text-gray-500 dark:border-gray-700">
          No corporate accounts yet — create one to invite employees and manage their stays.
        </p>
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          {accounts.map((account) => (
            <div
              key={account.id}
              className="flex flex-col gap-3 rounded-2xl border border-gray-200 bg-card p-5 dark:border-gray-800"
            >
              <div className="flex items-center justify-between">
                <div className="font-display font-bold text-foreground">{account.name}</div>
                <span
                  className={cn(
                    "rounded-full px-2 py-0.5 text-xs font-bold capitalize",
                    account.status === "active"
                      ? "bg-emerald-500/10 text-emerald-600"
                      : "bg-amber-500/10 text-amber-600"
                  )}
                >
                  {account.status}
                </span>
              </div>
              <div className="text-xs text-gray-600 dark:text-gray-400">
                {account.email} · {account.phone || "no phone"} · {account.address || "no address"}
              </div>
              <Button
                variant="outline"
                size="sm"
                onClick={() => setSelectedId(selectedId === account.id ? null : account.id)}
              >
                {selectedId === account.id ? "Hide members" : "Manage members"}
              </Button>
              {selectedId === account.id && (
                <div className="flex flex-col gap-2 border-t border-gray-100 pt-3 dark:border-gray-800">
                  <div className="flex gap-2">
                    <Input
                      value={inviteEmails}
                      onChange={(e) => setInviteEmails(e.target.value)}
                      placeholder="member@company.com, …"
                    />
                    <Button size="sm" onClick={submitInvite} disabled={addMembers.isPending}>
                      <UserPlus className="size-4" />
                    </Button>
                  </div>
                  <ul className="flex flex-col gap-1">
                    {members.map((m) => (
                      <li
                        key={m.id}
                        className="flex items-center justify-between rounded-lg bg-gray-50 px-3 py-1.5 text-xs dark:bg-gray-800"
                      >
                        <span className="font-medium text-foreground">{m.userName}</span>
                        <span className="text-gray-500">
                          {m.email} · {m.role}
                        </span>
                      </li>
                    ))}
                    {members.length === 0 && (
                      <li className="text-xs text-gray-500">No members yet.</li>
                    )}
                  </ul>
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      <div className="flex flex-col gap-3 rounded-2xl border border-gray-200 bg-card p-5 dark:border-gray-800">
        <h3 className="font-display font-bold text-foreground">Bulk booking</h3>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-5">
          <Input
            value={bulkForm.roomId}
            onChange={(e) => setBulkForm({ ...bulkForm, roomId: e.target.value })}
            placeholder="Room ID"
          />
          <Input
            value={bulkForm.members}
            onChange={(e) => setBulkForm({ ...bulkForm, members: e.target.value })}
            placeholder="Member IDs (1,2,3)"
            className="sm:col-span-2"
          />
          <Input
            type="date"
            value={bulkForm.from}
            onChange={(e) => setBulkForm({ ...bulkForm, from: e.target.value })}
          />
          <Input
            type="date"
            value={bulkForm.to}
            onChange={(e) => setBulkForm({ ...bulkForm, to: e.target.value })}
          />
        </div>
        <Button
          className="bg-orange-600 text-white hover:bg-orange-700"
          disabled={bulk.isPending}
          onClick={submitBulk}
        >
          {bulk.isPending ? <Loader2 className="size-4 animate-spin" /> : null} Place bulk booking
        </Button>
      </div>

      <div className="flex flex-col gap-2">
        <h3 className="flex items-center gap-2 font-display font-bold text-foreground">
          <FileText className="size-4 text-orange-600" /> Invoices
        </h3>
        {invoices.length === 0 ? (
          <p className="text-sm text-gray-500">No invoices yet.</p>
        ) : (
          <div className="overflow-x-auto rounded-2xl border border-gray-200 dark:border-gray-800">
            <table className="w-full min-w-[560px] text-sm">
              <thead className="bg-gray-50 text-left text-xs text-gray-500 dark:bg-gray-800">
                <tr>
                  <th className="px-4 py-2.5">Number</th>
                  <th className="px-4 py-2.5">Account</th>
                  <th className="px-4 py-2.5">Period</th>
                  <th className="px-4 py-2.5">Amount</th>
                  <th className="px-4 py-2.5">Status</th>
                  <th className="px-4 py-2.5" />
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
                {invoices.map((inv) => (
                  <tr key={inv.id}>
                    <td className="px-4 py-2.5 font-mono text-xs text-foreground">
                      {inv.invoiceNumber}
                    </td>
                    <td className="px-4 py-2.5 text-foreground">{inv.accountName}</td>
                    <td className="px-4 py-2.5 text-gray-500">
                      {inv.periodStart} → {inv.periodEnd}
                    </td>
                    <td className="px-4 py-2.5 font-semibold text-foreground">
                      ৳{inv.amount.toLocaleString()}
                    </td>
                    <td className="px-4 py-2.5 capitalize text-gray-600 dark:text-gray-400">
                      {inv.status}
                    </td>
                    <td className="px-4 py-2.5">
                      {inv.status === "draft" && (
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => generate.mutate(inv.id)}
                          disabled={generate.isPending}
                        >
                          Generate
                        </Button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
