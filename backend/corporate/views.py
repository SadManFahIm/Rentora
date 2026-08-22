"""Corporate housing endpoints (B2B accounts, RBAC, bulk booking, invoices)."""

from __future__ import annotations

from datetime import date

from django.conf import settings
from django.db import transaction
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from audit.services import log_action
from notifications.models import Notification
from notifications.utils import create_notification

from .models import CorporateAccount, CorporateInvoice, CorporateMember
from .serializers import (
    CorporateAccountSerializer,
    CorporateInvoiceSerializer,
    CorporateMemberSerializer,
)
from .services import (
    _is_admin,
    accounts_for,
    bulk_create_bookings,
    can_manage_account,
    generate_invoice,
    is_member,
)


def _get_account(request, pk) -> CorporateAccount | None:
    try:
        account = CorporateAccount.objects.get(pk=pk)
    except (CorporateAccount.DoesNotExist, TypeError, ValueError):
        return None
    if not is_member(request.user, account):
        return None
    return account


class CorporateAccountView(APIView):
    """Create a corporate account; list the accounts I belong to."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        if not getattr(settings, "CORPORATE_ENABLED", True):
            return Response(
                {"detail": "Corporate housing is not enabled."}, status=status.HTTP_403_FORBIDDEN
            )
        accounts = accounts_for(request.user)
        return Response(CorporateAccountSerializer(accounts, many=True).data)

    def post(self, request):
        if not getattr(settings, "CORPORATE_ENABLED", True):
            return Response(
                {"detail": "Corporate housing is not enabled."}, status=status.HTTP_403_FORBIDDEN
            )
        serializer = CorporateAccountSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        with transaction.atomic():
            account = serializer.save(owner=request.user)
            CorporateMember.objects.create(
                account=account, user=request.user, role=CorporateMember.Role.ADMIN
            )
        create_notification(
            user=request.user,
            notification_type=Notification.Type.CORPORATE_ACCOUNT_CREATED,
            title="Corporate account created",
            message=f"{account.name} is registered. Add members and book rooms in bulk.",
            action_url="/dashboard?tab=corporate",
        )
        log_action(actor=request.user, action="corporate.account_created", target=account)
        return Response(CorporateAccountSerializer(account).data, status=status.HTTP_201_CREATED)


class CorporateAccountDetailView(APIView):
    """Retrieve/update one corporate account (admins of the account)."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, pk):
        account = _get_account(request, pk)
        if account is None:
            return Response({"detail": "Account not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(CorporateAccountSerializer(account).data)

    def put(self, request, pk):
        account = _get_account(request, pk)
        if account is None:
            return Response({"detail": "Account not found."}, status=status.HTTP_404_NOT_FOUND)
        if not can_manage_account(request.user, account):
            return Response({"detail": "Account admin required."}, status=status.HTTP_403_FORBIDDEN)
        serializer = CorporateAccountSerializer(account, data=request.data, partial=True)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        serializer.save()
        log_action(actor=request.user, action="corporate.account_updated", target=account)
        return Response(CorporateAccountSerializer(account).data)


class CorporateMembersView(APIView):
    """List members; add a member by email (account admin only)."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, pk):
        account = _get_account(request, pk)
        if account is None:
            return Response({"detail": "Account not found."}, status=status.HTTP_404_NOT_FOUND)
        members = CorporateMember.objects.filter(account=account).select_related("user")
        return Response(CorporateMemberSerializer(members, many=True).data)

    def post(self, request, pk):
        account = _get_account(request, pk)
        if account is None:
            return Response({"detail": "Account not found."}, status=status.HTTP_404_NOT_FOUND)
        if not can_manage_account(request.user, account):
            return Response({"detail": "Account admin required."}, status=status.HTTP_403_FORBIDDEN)

        from .services import _get_or_create_member_user

        user = _get_or_create_member_user(
            {
                "email": request.data.get("email"),
                "first_name": request.data.get("first_name", ""),
                "last_name": request.data.get("last_name", ""),
                "phone": request.data.get("phone", ""),
            }
        )
        role = request.data.get("role", CorporateMember.Role.MEMBER)
        if role not in CorporateMember.Role.values:
            return Response(
                {"detail": "role must be admin or member."}, status=status.HTTP_400_BAD_REQUEST
            )
        member, created = CorporateMember.objects.get_or_create(
            account=account, user=user, defaults={"role": role}
        )
        if not created:
            member.role = role
            member.save(update_fields=["role"])
        log_action(
            actor=request.user,
            action="corporate.member_added",
            target=account,
            detail={"user_id": user.pk},
        )
        return Response(CorporateMemberSerializer(member).data, status=status.HTTP_201_CREATED)


class CorporateBulkBookingView(APIView):
    """Create PENDING bookings for a list of members (partial success)."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        if not getattr(settings, "CORPORATE_ENABLED", True):
            return Response(
                {"detail": "Corporate housing is not enabled."}, status=status.HTTP_403_FORBIDDEN
            )
        account = _get_account(request, request.data.get("account_id"))
        if account is None:
            return Response({"detail": "Account not found."}, status=status.HTTP_404_NOT_FOUND)
        if not can_manage_account(request.user, account):
            return Response({"detail": "Account admin required."}, status=status.HTTP_403_FORBIDDEN)

        from rooms.models import Room

        try:
            room = Room.objects.get(pk=request.data.get("room_id"))
        except (Room.DoesNotExist, TypeError, ValueError):
            return Response({"detail": "Room not found."}, status=status.HTTP_404_NOT_FOUND)

        members = request.data.get("members")
        if not isinstance(members, list) or not members:
            return Response(
                {"detail": "members must be a non-empty JSON array."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            check_in = date.fromisoformat(request.data.get("check_in"))
        except (TypeError, ValueError):
            return Response(
                {"check_in": "check_in must be a YYYY-MM-DD date."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        check_out_raw = request.data.get("check_out")
        check_out = date.fromisoformat(check_out_raw) if check_out_raw else None

        result = bulk_create_bookings(
            account=account,
            room=room,
            check_in=check_in,
            check_out=check_out,
            members=members,
            notes=request.data.get("notes", ""),
        )
        log_action(
            actor=request.user,
            action="corporate.bulk_booking",
            target=account,
            detail={"room_id": room.pk, "created_count": result["created_count"]},
        )
        return Response(
            result,
            status=status.HTTP_201_CREATED if result["created"] else status.HTTP_400_BAD_REQUEST,
        )


class CorporateInvoicesView(APIView):
    """List invoices for accounts I belong to; generate one for a period."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        accounts = accounts_for(request.user)
        invoices = CorporateInvoice.objects.filter(account__in=accounts)
        account_id = request.query_params.get("account_id")
        if account_id:
            invoices = invoices.filter(account_id=account_id)
        return Response(CorporateInvoiceSerializer(invoices, many=True).data)

    def post(self, request):
        account = _get_account(request, request.data.get("account_id"))
        if account is None:
            return Response({"detail": "Account not found."}, status=status.HTTP_404_NOT_FOUND)
        if not can_manage_account(request.user, account):
            return Response({"detail": "Account admin required."}, status=status.HTTP_403_FORBIDDEN)
        try:
            period_start = date.fromisoformat(request.data.get("period_start"))
            period_end = date.fromisoformat(request.data.get("period_end"))
        except (TypeError, ValueError):
            return Response(
                {"detail": "period_start and period_end must be YYYY-MM-DD dates."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        invoice = generate_invoice(account, period_start, period_end)
        log_action(actor=request.user, action="corporate.invoice_generated", target=invoice)
        return Response(CorporateInvoiceSerializer(invoice).data)


class CorporateAdminView(APIView):
    """Platform-admin view: all accounts + status control."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        if not _is_admin(request.user):
            return Response({"detail": "Admin access required."}, status=status.HTTP_403_FORBIDDEN)
        accounts = CorporateAccount.objects.all()
        return Response(
            {
                "accounts": CorporateAccountSerializer(accounts, many=True).data,
                "pending_count": accounts.filter(status=CorporateAccount.Status.PENDING).count(),
            }
        )

    def post(self, request):
        if not _is_admin(request.user):
            return Response({"detail": "Admin access required."}, status=status.HTTP_403_FORBIDDEN)
        try:
            account = CorporateAccount.objects.get(pk=request.data.get("account_id"))
        except (CorporateAccount.DoesNotExist, TypeError, ValueError):
            return Response({"detail": "Account not found."}, status=status.HTTP_404_NOT_FOUND)
        action = request.data.get("action")
        if action == "activate":
            account.status = CorporateAccount.Status.ACTIVE
        elif action == "suspend":
            account.status = CorporateAccount.Status.SUSPENDED
        else:
            return Response(
                {"detail": "action must be 'activate' or 'suspend'."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        account.save(update_fields=["status", "updated_at"])
        log_action(actor=request.user, action=f"corporate.{action}", target=account)
        return Response(CorporateAccountSerializer(account).data)
