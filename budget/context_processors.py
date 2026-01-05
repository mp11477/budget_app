def kiosk_flag(request):
    return {"is_kiosk": request.GET.get("kiosk") == "1"}