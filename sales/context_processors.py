from django.conf import settings


def company(request):
    return {
        "COMPANY_NAME": settings.COMPANY_NAME,
        "COMPANY_MOTTO": settings.COMPANY_MOTTO,
        "COMPANY_PHONE": settings.COMPANY_PHONE,
        "COMPANY_ADDRESS": settings.COMPANY_ADDRESS,
    }
