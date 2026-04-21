class NoCacheExamMiddleware:
    """
    Add no-cache headers to all exam pages so browser
    cannot go back to cached exam pages.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        # Apply to all student exam URLs
        path = request.path
        exam_paths = ['/attempt/', '/exam/']
        if any(path.startswith(p) for p in exam_paths):
            response['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
            response['Pragma'] = 'no-cache'
            response['Expires'] = '0'
        return response
