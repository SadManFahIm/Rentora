"""Insurance & credit endpoints."""

from __future__ import annotations

from django.conf import settings
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import InsuranceProduct, InsuranceQuote, Partner
from .serializers import InsuranceProductSerializer, InsuranceQuoteSerializer
from .services import PartnerServiceError, check_credit_eligibility, issue_policy


class InsuranceProductsView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        products = InsuranceProduct.objects.filter(
            is_active=True, partner__enabled=True, partner__kind=Partner.Kind.INSURANCE
        ).select_related("partner")
        return Response(InsuranceProductSerializer(products, many=True).data)


class InsuranceQuoteView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        quotes = InsuranceQuote.objects.filter(user=request.user).select_related(
            "product", "product__partner"
        )
        return Response(InsuranceQuoteSerializer(quotes, many=True).data)

    def post(self, request):
        if not getattr(settings, "INSURANCE_ENABLED", True):
            return Response(
                {"detail": "Insurance services are not enabled."}, status=status.HTTP_403_FORBIDDEN
            )
        serializer = InsuranceQuoteSerializer(data=request.data, context={"request": request})
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        quote = serializer.save()
        return Response(InsuranceQuoteSerializer(quote).data, status=status.HTTP_201_CREATED)


class InsuranceQuoteActionView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        try:
            quote = InsuranceQuote.objects.select_related("product", "product__partner").get(pk=pk)
        except (InsuranceQuote.DoesNotExist, TypeError, ValueError):
            return Response({"detail": "Quote not found."}, status=status.HTTP_404_NOT_FOUND)
        if quote.user_id != request.user.id and not (
            request.user.is_staff or request.user.role == request.user.Role.ADMIN
        ):
            return Response({"detail": "Not allowed."}, status=status.HTTP_403_FORBIDDEN)

        action = request.query_params.get("action") or request.data.get("action")
        if action == "issue":
            try:
                quote = issue_policy(quote, request.user)
            except PartnerServiceError as exc:
                return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
            return Response(InsuranceQuoteSerializer(quote).data)
        if action == "cancel":
            if quote.status != InsuranceQuote.Status.QUOTED:
                return Response(
                    {"detail": f"Cannot cancel a {quote.status} quote."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            quote.status = InsuranceQuote.Status.CANCELED
            quote.save(update_fields=["status", "updated_at"])
            return Response(InsuranceQuoteSerializer(quote).data)

        return Response(
            {"detail": "action must be 'issue' or 'cancel'."}, status=status.HTTP_400_BAD_REQUEST
        )


class CreditEligibilityView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        if not getattr(settings, "CREDIT_ENABLED", True):
            return Response(
                {"detail": "Credit services are not enabled."}, status=status.HTTP_403_FORBIDDEN
            )
        return Response(check_credit_eligibility(request.user))
