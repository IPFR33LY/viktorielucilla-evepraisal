$.tablesorter.addParser({
	// set a unique id 
	id: 'attrib',
	is: function (s, table, cell) {
        return !!s(cell).attr('data-sort');
	},
	format: function (s, table, cell) {
		return $(cell).attr('data-sort');
	},
	// set type, either numeric or text 
	type: 'numeric'
});