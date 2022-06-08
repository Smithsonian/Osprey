<script type="text/javascript">
    ;(function($) {
        $("#zoomimage").imgViewer({
            onClick: function( e, self ) {
                var pos = self.cursorToImg( e.pageX, e.pageY);
                $("#position").html(e.pageX + " " + e.pageY + " " + pos.relx + " " + pos.rely);
            }
        });
    })(jQuery);
</script>
