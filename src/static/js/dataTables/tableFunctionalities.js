$(".filter-btn").click(e => {
    e.stopPropagation()
    button = e.currentTarget
    labelContainer = button.parentElement
    icon = button.querySelector("img")
    filterBox = button.parentElement.nextElementSibling
    if (filterBox.getAttribute("display-state") === "visible") {
        filterBox.style.display = "none"
        filterBox.setAttribute("display-state", "hidden")
        if (button.getAttribute("filter-state") == "inactive") {
            icon.setAttribute("src", "/static/img/filtericon.svg")
        }
    }
    else {
        filterBox.style.display = "block"
        filterBox.setAttribute("display-state", "visible")
        icon.setAttribute("src", "/static/img/filtericon_selected.svg")
        var position = $(button).offset()
        if (filterBox.classList.contains("left")) {
            $(filterBox).css({
                'margin-left': position.left - 9 + 'px',
                'margin-top': position.top + 40 + 'px',
                'top': 0,
                'left': 0,
            });
        }
        else {
            $(filterBox).css({
                'margin-left': position.left - 141 + 'px',
                'margin-top': position.top + 40 + 'px',
                'top': 0,
                'left': 0,
            });
        }
    }
})


$(".filter-window").click(e => {
    if ($(e.target).closest('.nice-select').length === 0) {
        $('.nice-select').removeClass('open').find('.option');  
    }
    e.stopPropagation()
})


$(".nice-select.filter-op").click(e => {
    var dropdown = $(e.currentTarget)
    if ($(".nice-select.filter-op").is(e.currentTarget)) {
        $(".nice-select").not(dropdown).removeClass('open');
        dropdown.toggleClass('open');
        if (dropdown.hasClass('open')) {
            dropdown.find('.option');  
            dropdown.find('.focus').removeClass('focus');
            dropdown.find('.selected').addClass('focus');
        } else {
            dropdown.focus();
        }
    }
})


$(".nice-select.filter-op .option:not(.disabled)").click(e => {
    e.stopPropagation()
    var $option = $(e.currentTarget);
    var $dropdown = $option.closest('.nice-select');
      
    $dropdown.find('.selected').removeClass('selected');
    $option.addClass('selected');
      
    var text = $option.data('display') || $option.text();
    
    $dropdown.find('.current').text(text);
    if ($option.data('value') !== $dropdown.prev('select').val()) {
        $dropdown.prev('select').val($option.data('value')).trigger('change');
    }
    $dropdown.removeClass("open")

})


$("select.filter-op").change(e => {
    $dropdown = $(e.target)
    minEle = $dropdown.parent().siblings(".form-input").find('input[value-type="min"]')
    maxEle = $dropdown.parent().siblings(".form-input").find('input[value-type="max"]')
    if ($dropdown.val() === "gte") {
        minEle.show()
        maxEle.hide()
        maxEle.val("")
        minEle.val("")
        maxEle.attr("placeholder", "Filter")
        minEle.attr("placeholder", "Filter")
    }
    if ($dropdown.val() === "lte") {
        maxEle.show()
        minEle.hide()
        maxEle.val("")
        minEle.val("")
        maxEle.attr("placeholder", "Filter")
        minEle.attr("placeholder", "Filter")
    }
    if ($dropdown.val() === "range") {
        maxEle.show()
        minEle.show()
        maxEle.val("")
        minEle.val("")
        maxEle.attr("placeholder", "Maximum")
        minEle.attr("placeholder", "Minimum")
    }
    if ($dropdown.val() === "equal") {
        minEle.show()
        maxEle.hide()
        maxEle.val("")
        minEle.val("")
        maxEle.attr("placeholder", "Filter")
        minEle.attr("placeholder", "Filter")
        maxEle.val(minEle.val())
    }
})


$(".filter-input[type='checkbox']").change(e => {
    table.draw()
})


$(".filter-input[value-type='min']").on("keyup", (e => {
    minEle = $(e.target)
    filterOp = minEle.parent().siblings(".form-input").find('select.filter-op')
    maxEle = minEle.parent().siblings(".form-input").find('input[value-type="max"]')
    if (filterOp.val() === "equal") {
        maxEle.val(minEle.val())
    }
    else {
        maxEle.val("")
    }
}))


$(".filter-input[value-type]").keypress(e => {
    if (e.which === 13) {
        e.stopPropagation()
    }
})


$(".filter-input[value-type]").keyup(e => {
    filterInput = $(e.target)
    filterCol =filterInput.parent().parent().attr("filter-col")
    if (filterInput.val() === "" && filteredColumns.includes(filterCol)) {
        index = filteredColumns.indexOf(filterCol)
        filteredColumns.splice(index, 1);
    }
    else if (filterInput.val() !== "" && !(filteredColumns.includes(filterCol))) {
        filteredColumns.push(filterCol)
    }
    table.draw()
})


$("input.filter-input").on("keyup, change", e => {
    input = e.currentTarget
    filterBox = input.closest(".filter-window")
    button = filterBox.previousElementSibling.querySelector("button")
    inputs = filterBox.getElementsByTagName("input")
    for (var i = 0; i < inputs.length; i++) {
        if ((inputs[i].getAttribute("type") === "checkbox" && inputs[i].checked) || (inputs[i].getAttribute("type") === "text" && inputs[i].value !== "")) {
            button.setAttribute("filter-state", "active")
            return
        }
    }
    button.setAttribute("filter-state", "inactive")
})