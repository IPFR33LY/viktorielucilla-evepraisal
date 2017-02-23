from . import app, views, api


# Login stuff

app.route('/login')(views.login)
app.route('/logout')(views.logout)
app.route('/callback')(views.openauth_callback)

# Main site stuff
app.route('/', methods=['GET', 'POST'])(views.index)
app.route('/history')(views.history)
app.route('/options', methods=['GET', 'POST'])(views.options)
app.route('/estimate', methods=['POST'])(views.estimate_cost)
app.route('/e/<int:result_id>')(views.display_result)
app.route('/estimate/<int:result_id>', methods=['GET'])(views.display_result)
app.route('/latest')(views.latest)
app.route('/legal')(views.legal)

# Static Stuff (should really be served from a legit file server)
app.route('/robots.txt')(views.static_from_root)
app.route('/favicon.ico')(views.static_from_root)

# Current Version
app.route('/e/<int:result_id>.json', methods=['GET'])(api.estimate_v2)
app.route('/e/<int:result_id>.csv', methods=['GET'])(api.estimate_csv_v2)
app.route('/api/estimate/<int:result_id>', methods=['GET'])(api.estimate_v2)
app.route('/api/estimate/create', methods=['POST'])(api.estimate_create_v2)
app.route('/api/estimate/history', methods=['GET'])(api.estimate_history_v2)
app.route('/api/estimate/history.csv', methods=['GET'])(api.estimate_history_csv_v2)

# v1
app.route('/api/v1/estimate/<int:result_id>', methods=['GET'])(api.estimate_v1)
app.route('/api/v1/estimate/create', methods=['POST'])(api.estimate_create_v1)
app.route('/api/v1/estimate/history', methods=['GET'])(api.estimate_history_v1)

# v2
app.route('/api/v2/estimate/<int:result_id>', methods=['GET'])(api.estimate_v2)
app.route('/api/v2/estimate/<int:result_id>.csv')(api.estimate_csv_v2)
app.route('/api/v2/estimate/create', methods=['POST'])(api.estimate_create_v2)
app.route('/api/v2/estimate/history', methods=['GET'])(api.estimate_history_v2)
app.route('/api/v2/estimate/history.csv', methods=['GET'])(api.estimate_history_csv_v2)
