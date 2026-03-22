"""
訂單 API 視圖
"""
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from .serializers import OrderCreateSerializer, OrderSerializer


class OrderCreateView(APIView):
    """建立新訂單（允許訪客購買）"""
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = OrderCreateSerializer(
            data=request.data,
            context={'user': request.user if request.user.is_authenticated else None}
        )
        if serializer.is_valid():
            order = serializer.save()
            response_serializer = OrderSerializer(order)
            return Response(
                {
                    'message': '訂單建立成功！我們將儘快與您聯繫。',
                    'order': response_serializer.data
                },
                status=status.HTTP_201_CREATED
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
