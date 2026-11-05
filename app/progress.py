"""Human-readable progress from actual host operations, never model guesses."""

TOOL_ACTIVITY = {
    'search_stores': '正在查麦当劳门店',
    'recommend_meals': '正在查麦当劳餐品和价格',
    'choose_meal': '正在核对餐品和价格，还没有下单',
    'cancel_plan': '正在撤下待确认方案，不会取消已有订单',
    'mcd_search_pickup': '正在查麦当劳到店门店',
    'mcd_delivery_addresses': '正在查您已有的麦当劳配送地址',
    'mcd_delivery_stores': '正在查这个地址可配送的麦当劳门店',
    'mcd_menu': '正在查麦当劳菜单',
    'mcd_product_detail': '正在查餐品规格和可选搭配',
    'mcd_prepare_order': '正在核对麦当劳餐品和总价，还没有下单',
    'mcd_orders': '正在查您已有的麦当劳订单',
    'mcd_order_status': '正在查麦当劳订单状态',
    'mcd_prepare_cancel': '正在核对麦当劳取消条件，还没有取消订单',
    'luckin_search_stores': '正在查瑞幸门店',
    'luckin_search_products': '正在查瑞幸饮品',
    'luckin_product_detail': '正在查饮品规格',
    'luckin_switch_product': '正在核对饮品温度和甜度选项',
    'luckin_preview': '正在查瑞幸价格，还没有下单',
    'luckin_prepare_order': '正在核对瑞幸饮品和总价，还没有下单',
    'luckin_query_order': '正在查瑞幸订单状态',
    'luckin_order_records': '正在查您已有的瑞幸订单',
    'luckin_prepare_cancel': '正在核对瑞幸取消条件，还没有取消订单',
    'didi_search_places': '正在查地点，请稍后核对上下车位置',
    'didi_estimate_ride': '正在查滴滴车型和预估费用，还没有叫车',
    'didi_prepare_ride': '正在核对行程和预估费用，还没有叫车',
    'didi_query_ride': '正在查滴滴行程状态',
    'didi_driver_location': '正在查司机位置',
    'didi_list_rides': '正在查您已有的滴滴行程',
    'didi_prepare_cancel': '正在核对行程取消条件，还没有取消叫车',
    'personal_profile': '正在处理您明确要求查看或修改的个人资料',
    'task_records': '正在查您已有的办事记录',
}


def tool_activity(name):
    # Never show tool arguments, credentials, or raw provider output as status.
    return {'type': 'progress', 'stage': 'tool',
            'text': TOOL_ACTIVITY.get(name, '正在处理这一步，请稍等')}
